from __future__ import annotations

import argparse
import asyncio
import logging
import random
import re
import sys
from pathlib import Path

from rich.console import Console

from rjobs import __version__
from rjobs.config import (DEFAULT_CONFIG_PATH, load_config,
                          write_cookie_templates, write_template_config)
from rjobs.models import JobListing, Source
from rjobs.output import display_table, to_csv, to_json
from rjobs.profile import (digest_resume, extract_text_from_file,
                           is_linkedin_profile_url, load_profile, save_profile,
                           scrape_linkedin_profile)
from rjobs.ranking import rank_jobs
from rjobs.scrapers import build_http_client, get_scrapers

logger = logging.getLogger("rjobs")
console = Console()

VALID_SOURCES = [s.value for s in Source]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rjobs",
        description="Search and rank remote job opportunities across multiple sources.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=f"Path to config.yml (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--init-config",
        nargs="?",
        const="default",
        metavar="PATH",
        help="Generate a template config.yml and exit",
    )
    parser.add_argument(
        "--init-cookies",
        action="store_true",
        help="Create cookie template files under ~/.config/rjobs/cookies/ and exit",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        default=None,
        help="Extra search keywords (appended to config keywords)",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        default=None,
        choices=VALID_SOURCES,
        metavar="SOURCE",
        help="Limit to specific sources",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Max number of results to display",
    )
    parser.add_argument(
        "--max-listings",
        type=int,
        default=None,
        help="Randomly sample listings to this count before ranking (useful for debugging)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        help="Minimum rank threshold (0-10)",
    )
    parser.add_argument(
        "--no-rank",
        action="store_true",
        help="Skip LLM ranking",
    )
    parser.add_argument(
        "--export",
        type=Path,
        default=None,
        metavar="FILE",
        help="Export results to a file (format inferred from extension)",
    )
    parser.add_argument(
        "--parse-resume",
        type=str,
        default=None,
        metavar="FILE_OR_URL",
        help="Parse a resume (PDF, Markdown, or plain text) or a LinkedIn profile URL "
             "and save an applicant profile for ranking",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="default",
        metavar="NAME",
        help="Applicant profile name (default: 'default'). Used with --parse-resume and during ranking.",
    )
    parser.add_argument(
        "--show-reasoning",
        action="store_true",
        help="Show LLM ranking reasoning in table output",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)",
    )
    return parser


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _handle_init_config(args: argparse.Namespace) -> None:
    if args.init_config == "default":
        path = args.config or DEFAULT_CONFIG_PATH
    else:
        path = Path(args.init_config)

    out_path = write_template_config(path)
    console.print(f"[green]Config template written to:[/green] {out_path}")
    console.print("Edit it with your credentials and preferences, then run rjobs again.")
    sys.exit(0)


async def _handle_parse_resume(args: argparse.Namespace) -> None:
    resume_input = args.parse_resume
    config = load_config(args.config)

    if is_linkedin_profile_url(resume_input):
        console.print(f"[bold]Scraping LinkedIn profile: {resume_input}...[/bold]")
        resume_text = await scrape_linkedin_profile(resume_input, config)
        if not resume_text.strip():
            console.print("[red]Could not extract any text from the LinkedIn profile.[/red]")
            sys.exit(1)
    else:
        resume_path = Path(resume_input)
        if not resume_path.exists():
            console.print(f"[red]Resume file not found:[/red] {resume_path}")
            sys.exit(1)

        console.print(f"[bold]Reading resume from {resume_path}...[/bold]")
        resume_text = extract_text_from_file(resume_path)
        if not resume_text.strip():
            console.print("[red]Could not extract any text from the resume file.[/red]")
            sys.exit(1)

    console.print(f"[bold]Digesting resume via LLM ({config.llm.model})...[/bold]")
    profile = await digest_resume(resume_text, config)

    out_path = save_profile(profile, args.profile)
    console.print(f"\n[green]Applicant profile saved to:[/green] {out_path}")
    console.print("\n[bold]Profile summary:[/bold]")
    console.print(f"  Name: {profile.name}")
    console.print(f"  Summary: {profile.summary}")
    if profile.target_roles:
        console.print(f"  Target roles: {', '.join(profile.target_roles)}")
    if profile.skills:
        console.print(f"  Skills: {', '.join(profile.skills[:10])}{'...' if len(profile.skills) > 10 else ''}")
    if profile.role_keywords:
        console.print(f"  Role keywords: {', '.join(profile.role_keywords)}")
    console.print("\nThis profile will be used to personalize job ranking and search.")
    sys.exit(0)


# Location patterns that indicate a truly remote position
_REMOTE_INDICATORS = re.compile(
    r"\b(remote|worldwide|anywhere|global|distributed|work from home|wfh)\b",
    re.IGNORECASE,
)

# Words commonly found in software/tech job titles.  Used both for deriving
# role keywords from target_roles *and* for broadening the title-relevance
# filter so that multi-word keywords like "graphics engineer" also let
# through "Senior Software Engineer" (via the "engineer" component).
_SOFTWARE_ROLE_WORDS = frozenset({
    "engineer", "developer", "programmer", "architect",
    "devops", "sre", "scientist", "hacker", "coder",
})

# Seniority / prefix words stripped when deriving keywords from target_roles.
_SENIORITY_PREFIXES = re.compile(
    r"^(senior|junior|lead|principal|staff|chief|head|vp|intern)\s+",
    re.IGNORECASE,
)


def _derive_role_keywords(profile) -> list[str]:
    """Derive useful search keywords from *target_roles* when role_keywords is empty."""
    keywords: list[str] = []
    for role in profile.target_roles:
        # Full role (minus seniority prefix) as a keyword
        cleaned = _SENIORITY_PREFIXES.sub("", role).strip()
        if cleaned:
            keywords.append(cleaned.lower())
    return list(dict.fromkeys(keywords))  # dedupe, preserve order


def _is_remote_location(location: str | None) -> bool:
    """Return True if *location* contains a remote indicator."""
    if not location:
        # No location info – give benefit of the doubt
        return True
    return bool(_REMOTE_INDICATORS.search(location))


def _filter_remote(jobs: list[JobListing]) -> list[JobListing]:
    """Discard listings whose location lacks any remote indicator."""
    kept = [j for j in jobs if _is_remote_location(j.location)]
    removed = len(jobs) - len(kept)
    if removed:
        logger.info(
            "Remote-only filter removed %d/%d listings with non-remote locations",
            removed,
            len(jobs),
        )
    return kept


def _filter_title_relevance(
    jobs: list[JobListing], role_keywords: list[str]
) -> list[JobListing]:
    """Keep only listings whose title matches at least one role keyword.

    This is the last line of defence against non-relevant jobs that slip
    through broad API searches or description-based keyword matching.

    In addition to matching full keywords as substrings, individual words
    that belong to ``_SOFTWARE_ROLE_WORDS`` are extracted from multi-word
    keywords and used as additional matchers.  This means a keyword such as
    "graphics engineer" also lets through "Senior Software Engineer" because
    the word "engineer" is recognised as a software-role indicator.
    """
    if not role_keywords:
        return jobs

    kw_lower = [kw.lower() for kw in role_keywords]

    # Extract individual role-indicator words for broader matching
    role_words: set[str] = set()
    for kw in kw_lower:
        for word in kw.split():
            if word in _SOFTWARE_ROLE_WORDS:
                role_words.add(word)

    all_matchers = list(dict.fromkeys(kw_lower + sorted(role_words)))

    kept = [
        j for j in jobs
        if any(m in j.title.lower() for m in all_matchers)
    ]
    removed = len(jobs) - len(kept)
    if removed:
        logger.info(
            "Title relevance filter removed %d/%d listings not matching role keywords",
            removed,
            len(jobs),
        )
    return kept


def _deduplicate(jobs: list[JobListing]) -> list[JobListing]:
    seen: dict[str, JobListing] = {}
    for job in jobs:
        key = job.dedup_key
        if key in seen:
            existing = seen[key]
            # Keep the one with more info
            if len(job.description) > len(existing.description):
                seen[key] = job
        else:
            seen[key] = job

    deduped = list(seen.values())
    removed = len(jobs) - len(deduped)
    if removed:
        logger.info("Deduplicated %d listings -> %d unique", len(jobs), len(deduped))
    return deduped


async def _run(args: argparse.Namespace) -> None:
    # Load config
    config = load_config(args.config)

    # If config doesn't exist and no explicit path, offer to create template
    config_path = args.config or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        console.print(
            f"[yellow]No config found at {config_path}.[/yellow]\n"
            f"Run [bold]rjobs --init-config[/bold] to generate a template."
        )

    # Merge CLI keyword overrides
    search_keywords = list(config.search.keywords)
    if args.keywords:
        search_keywords.extend(args.keywords)

    # Inject role keywords from the applicant profile
    profile = load_profile(args.profile)
    role_keywords: list[str] = []
    if profile:
        if profile.role_keywords:
            role_keywords = list(profile.role_keywords)
        elif profile.target_roles:
            role_keywords = _derive_role_keywords(profile)
            logger.info("Derived role keywords from target_roles: %s", role_keywords)
        if role_keywords:
            logger.info("Role keywords for profile '%s': %s", args.profile, role_keywords)

    # When role keywords exist, use ONLY role keywords (plus any explicit
    # --keywords from the CLI).  The default search keywords like "remote",
    # "worldwide", "global" etc. are useless on remote-specific job boards
    # and cause every listing to match, drowning out the role filter.
    if role_keywords:
        cli_extra = list(args.keywords) if args.keywords else []
        keywords = list(dict.fromkeys(role_keywords + cli_extra))
    else:
        keywords = list(dict.fromkeys(search_keywords))

    threshold = args.threshold if args.threshold is not None else config.ranking.threshold

    # Build scrapers
    async with build_http_client() as client:
        scrapers = get_scrapers(config, client, args.sources)

        if not scrapers:
            console.print("[red]No scrapers selected. Check --sources or config.[/red]")
            return

        console.print(
            f"[bold]Searching {len(scrapers)} sources with " f"{len(keywords)} keywords...[/bold]\n"
        )

        # Run all scrapers concurrently
        all_jobs: list[JobListing] = []
        total_scrapers = len(scrapers)
        completed = 0

        async def _run_scraper(scraper):
            nonlocal completed
            try:
                result = await scraper.search(keywords)
            except Exception as e:
                logger.error("%s raised: %s", scraper.source.value, e)
                result = e
            completed += 1
            count = len(result) if isinstance(result, list) else 0
            console.print(f"  Scraped source {completed}/{total_scrapers} ({scraper.source.value}) - {count} listings")
            return scraper, result

        outcomes = await asyncio.gather(*[_run_scraper(s) for s in scrapers])

        for scraper, result in outcomes:
            if isinstance(result, Exception):
                pass  # already logged above
            elif isinstance(result, list):
                all_jobs.extend(result)

        console.print(f"  Found {len(all_jobs)} listings")

        # Deduplicate
        all_jobs = _deduplicate(all_jobs)

        # Pre-filter: discard non-remote locations
        if config.filter.remote_only:
            all_jobs = _filter_remote(all_jobs)
            console.print(f"  {len(all_jobs)} listings after remote-only filter")

        # Pre-filter: discard jobs whose title doesn't match any role keyword
        if role_keywords:
            all_jobs = _filter_title_relevance(all_jobs, role_keywords)
            console.print(f"  {len(all_jobs)} listings after title relevance filter")

        # Randomly sample if --max-listings is set (pre-ranking filter)
        if args.max_listings and len(all_jobs) > args.max_listings:
            all_jobs = random.sample(all_jobs, args.max_listings)
            console.print(f"  Sampled {args.max_listings} listings (--max-listings)")

        # Rank with LLM
        if not args.no_rank and all_jobs:
            console.print(f"\n[bold]Ranking {len(all_jobs)} listings via LLM ({config.llm.model})...[/bold]")
            try:
                all_jobs = await rank_jobs(
                    all_jobs,
                    config,
                    args.profile,
                    on_progress=lambda done, total: console.print(
                        f"  Ranked batch {done}/{total}"
                    ),
                )
            except Exception as e:
                logger.error("LLM ranking failed: %s", e)
                console.print("[yellow]LLM ranking failed - showing unranked results.[/yellow]")

        # Sort: ranked first (desc), then unranked
        all_jobs.sort(key=lambda j: (j.rank is not None, j.rank or 0), reverse=True)

        # Filter by threshold
        if not args.no_rank:
            before = len(all_jobs)
            all_jobs = [j for j in all_jobs if j.rank is None or j.rank >= threshold]
            filtered = before - len(all_jobs)
            if filtered:
                logger.info("Filtered out %d jobs below threshold %d", filtered, threshold)

        # Limit results
        if args.max_results and len(all_jobs) > args.max_results:
            all_jobs = all_jobs[: args.max_results]

    # Output
    _output_results(all_jobs, args)


def _output_results(jobs: list[JobListing], args: argparse.Namespace) -> None:
    fmt = args.format

    if args.export:
        ext = args.export.suffix.lower()
        if ext == ".json":
            content = to_json(jobs)
        elif ext == ".csv":
            content = to_csv(jobs)
        else:
            content = to_json(jobs)

        args.export.parent.mkdir(parents=True, exist_ok=True)
        args.export.write_text(content)
        console.print(f"[green]Exported {len(jobs)} results to {args.export}[/green]")

    if fmt == "json":
        print(to_json(jobs))
    elif fmt == "csv":
        print(to_csv(jobs))
    else:
        display_table(jobs, show_reasoning=args.show_reasoning)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    _setup_logging(args.verbose)

    if args.init_config is not None:
        _handle_init_config(args)

    if args.init_cookies:
        out_dir = write_cookie_templates()
        console.print(f"[green]Cookie templates created in:[/green] {out_dir}")
        console.print(
            "Paste your browser cookie strings into the files there.\n"
            "See instructions inside each file for how to export cookies."
        )
        sys.exit(0)

    if args.parse_resume is not None:
        try:
            asyncio.run(_handle_parse_resume(args))
        except Exception as e:
            console.print(f"[red]Failed to parse resume:[/red] {e}")
            sys.exit(1)
        return

    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
