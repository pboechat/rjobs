from __future__ import annotations

import json
import logging
from collections.abc import Callable

from openai import AsyncOpenAI

from rjobs.config import DEFAULT_SYSTEM_PROMPT, Config
from rjobs.models import JobListing
from rjobs.profile import load_profile

logger = logging.getLogger(__name__)

BATCH_SIZE = 15

APPLICANT_RANKING_ADDENDUM = """

You also have the applicant's profile below. Use it to personalize your ranking:
- Prioritize listings that match the applicant's skills and experience areas
- Favor roles that align with their target roles
- Consider their stated preferences (remote style, location, etc.)
- Weigh compensation transparency and role seniority fit

--- APPLICANT PROFILE ---
{profile_context}
--- END APPLICANT PROFILE ---
"""


async def rank_jobs(
    jobs: list[JobListing],
    config: Config,
    profile_name: str = "default",
    on_progress: Callable[[int, int], None] | None = None,
) -> list[JobListing]:
    if not jobs:
        return jobs

    client = AsyncOpenAI(
        base_url=config.llm.base_url,
        api_key=config.llm.api_key or "not-needed",
    )

    ranked: list[JobListing] = []
    total_batches = (len(jobs) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        batch = jobs[start: start + BATCH_SIZE]
        logger.info("Ranking batch %d/%d (%d jobs)", batch_idx + 1, total_batches, len(batch))

        try:
            await _rank_batch(client, batch, config, profile_name)
        except Exception as e:
            logger.error("Ranking batch %d failed: %s", batch_idx + 1, e)
        ranked.extend(batch)

        if on_progress:
            on_progress(batch_idx + 1, total_batches)

    return ranked


async def _rank_batch(
    client: AsyncOpenAI,
    batch: list[JobListing],
    config: Config,
    profile_name: str = "default",
) -> None:
    listings_text = "\n\n".join(
        f"[{i}] Title: {j.title}\n"
        f"Company: {j.company}\n"
        f"Location: {j.location or 'N/A'}\n"
        f"Salary: {j.salary or 'N/A'}\n"
        f"Tags: {', '.join(j.tags) if j.tags else 'N/A'}\n"
        f"Source: {j.source.value}\n"
        f"Description: {j.description[:500]}"
        for i, j in enumerate(batch)
    )

    system_prompt = config.ranking.system_prompt or DEFAULT_SYSTEM_PROMPT

    # Inject applicant profile if available
    profile = load_profile(profile_name)
    if profile:
        context = profile.to_ranking_context()
        system_prompt += APPLICANT_RANKING_ADDENDUM.format(profile_context=context)
        logger.info("Injected applicant profile into ranking prompt")

    resp = await client.chat.completions.create(
        model=config.llm.model,
        temperature=config.llm.temperature,
        max_tokens=config.llm.max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Rank these job listings:\n\n{listings_text}"},
        ],
    )

    content = resp.choices[0].message.content or ""

    # Try to parse JSON from the response (handle markdown code blocks)
    json_str = content.strip()
    if json_str.startswith("```"):
        json_str = "\n".join(json_str.split("\n")[1:])
        if json_str.endswith("```"):
            json_str = json_str[:-3]

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning("Could not parse LLM ranking response as JSON\n"
                       "Raw response: %s", content)
        return

    # Handle {"rankings": [...]} or direct list [...]
    if isinstance(parsed, dict):
        rankings = parsed.get("rankings", parsed.get("results", []))
    elif isinstance(parsed, list):
        rankings = parsed
    else:
        logger.warning("Unexpected ranking format: %s", type(parsed))
        return

    rank_map: dict[int, dict] = {}
    for r in rankings:
        if isinstance(r, dict) and "index" in r and "rank" in r:
            rank_map[int(r["index"])] = r

    for i, job in enumerate(batch):
        if i in rank_map:
            raw_rank = float(rank_map[i]["rank"])
            job.rank = max(0.0, min(10.0, raw_rank))
            if raw_rank != job.rank:
                logger.warning(
                    "Clamped hallucinated rank %.1f -> %.1f for %s",
                    raw_rank, job.rank, job.title,
                )
            job.rank_reasoning = rank_map[i].get("reasoning", "")

    logger.debug("Ranked %d/%d jobs in batch", len(rank_map), len(batch))
