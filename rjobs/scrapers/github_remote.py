from __future__ import annotations

import re

from rjobs.models import JobListing, Source
from rjobs.scrapers.base import BaseScraper

RAW_URL = "https://raw.githubusercontent.com/yanirs/established-remote/master/README.md"
# Match markdown table rows: | Company | URL | Region | ... |
TABLE_ROW = re.compile(r"^\|(.+)\|$", re.MULTILINE)
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


class GitHubRemoteScraper(BaseScraper):
    source = Source.GITHUB_REMOTE

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        self.logger.debug("Fetching established-remote list from GitHub")
        resp = await self._get(RAW_URL)
        return self._parse_readme(resp.text, keywords)

    def _parse_readme(self, text: str, keywords: list[str]) -> list[JobListing]:
        kw_lower = {kw.lower() for kw in keywords}
        jobs: list[JobListing] = []

        in_table = False
        for line in text.split("\n"):
            stripped = line.strip()

            # Detect markdown table boundaries
            if stripped.startswith("|") and "---" in stripped:
                in_table = True
                continue
            if not stripped.startswith("|"):
                if in_table:
                    in_table = False
                continue
            if not in_table:
                # First row after header separator
                if stripped.startswith("|") and "|" in stripped[1:]:
                    in_table = True

            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if len(cells) < 2:
                continue

            # Extract company name and URL from first cell (may contain markdown link)
            name_cell = cells[0]
            link_match = LINK_PATTERN.search(name_cell)
            if link_match:
                company_name = link_match.group(1).strip()
                company_url = link_match.group(2).strip()
            else:
                company_name = name_cell.strip()
                company_url = ""

            region = cells[1].strip() if len(cells) > 1 else ""
            extra = cells[2].strip() if len(cells) > 2 else ""

            searchable = f"{company_name} {extra}".lower()
            if not any(kw in searchable for kw in kw_lower):
                continue

            jobs.append(
                JobListing(
                    title=f"{company_name} - Remote-friendly company",
                    company=company_name,
                    url=company_url or "https://github.com/yanirs/established-remote",
                    source=self.source,
                    location=region or "Various",
                    description=extra,
                    tags=["company_directory", "established_remote"],
                    remote_type="fully_remote",
                )
            )

        return jobs
