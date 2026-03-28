from __future__ import annotations

from datetime import datetime

from rjobs.models import JobListing, Source
from rjobs.scrapers.base import BaseScraper


class GreenhouseScraper(BaseScraper):
    source = Source.GREENHOUSE
    api_base = "https://boards-api.greenhouse.io/v1/boards"

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        companies = self.config.sources.ats_companies.greenhouse
        if not companies:
            self.logger.info("No Greenhouse company slugs configured - skipping")
            return []

        kw_lower = {kw.lower() for kw in keywords}
        jobs: list[JobListing] = []

        for company in companies:
            self.logger.debug("Querying Greenhouse board: %s", company)
            try:
                resp = await self._get(
                    f"{self.api_base}/{company}/jobs",
                    params={"content": "true"},
                )
                data = resp.json()

                for entry in data.get("jobs", []):
                    if self._matches(entry, kw_lower):
                        jobs.append(self._parse_entry(entry, company))
            except Exception as e:
                self.logger.debug("Greenhouse board '%s' failed: %s", company, e)

        return jobs

    def _matches(self, entry: dict, keywords: set[str]) -> bool:
        location = entry.get("location", {}).get("name", "")
        searchable = f"{entry.get('title', '')} {location}".lower()
        return any(kw in searchable for kw in keywords) or "remote" in searchable

    def _parse_entry(self, entry: dict, company: str) -> JobListing:
        location = entry.get("location", {})
        location_name = location.get("name", "Remote") if isinstance(location, dict) else "Remote"

        posted = None
        if updated := entry.get("updated_at"):
            try:
                posted = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return JobListing(
            title=entry.get("title", "Unknown"),
            company=company,
            url=entry.get("absolute_url", f"https://boards.greenhouse.io/{company}"),
            source=self.source,
            location=location_name,
            description=entry.get("content", ""),
            posted_date=posted,
        )
