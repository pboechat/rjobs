from __future__ import annotations

from datetime import datetime

from rjobs.models import JobListing, Source
from rjobs.scrapers.base import BaseScraper


class LeverScraper(BaseScraper):
    source = Source.LEVER
    api_base = "https://api.lever.co/v0/postings"

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        companies = self.config.sources.ats_companies.lever
        if not companies:
            self.logger.info("No Lever company slugs configured - skipping")
            return []

        kw_lower = {kw.lower() for kw in keywords}
        jobs: list[JobListing] = []

        for company in companies:
            self.logger.debug("Querying Lever board: %s", company)
            try:
                resp = await self._get(f"{self.api_base}/{company}")
                data = resp.json()

                entries = data if isinstance(data, list) else []
                for entry in entries:
                    if self._matches(entry, kw_lower):
                        jobs.append(self._parse_entry(entry, company))
            except Exception as e:
                self.logger.debug("Lever board '%s' failed: %s", company, e)

        return jobs

    def _matches(self, entry: dict, keywords: set[str]) -> bool:
        categories = entry.get("categories", {})
        commitment = categories.get("commitment", "") if isinstance(categories, dict) else ""
        searchable = f"{entry.get('text', '')} {commitment}".lower()
        return any(kw in searchable for kw in keywords)

    def _parse_entry(self, entry: dict, company: str) -> JobListing:
        categories = entry.get("categories", {})
        location = (
            categories.get("location", "Remote") if isinstance(categories, dict) else "Remote"
        )

        posted = None
        if ts := entry.get("createdAt"):
            try:
                posted = datetime.fromtimestamp(ts / 1000)
            except (ValueError, TypeError):
                pass

        salary = None
        additional = entry.get("additional", "")
        if additional and "$" in additional:
            salary = additional

        return JobListing(
            title=entry.get("text", "Unknown"),
            company=company,
            url=entry.get("hostedUrl", f"https://jobs.lever.co/{company}"),
            source=self.source,
            location=location,
            salary=salary,
            description=entry.get("descriptionPlain", ""),
            posted_date=posted,
        )
