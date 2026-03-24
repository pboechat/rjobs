from __future__ import annotations

from datetime import datetime, timezone

from remote_job_scraper.models import JobListing, Source
from remote_job_scraper.scrapers.base import BaseScraper


class RemoteOKScraper(BaseScraper):
    source = Source.REMOTEOK
    api_url = "https://remoteok.com/api"

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        self.logger.debug("GET %s", self.api_url)
        resp = await self._get(
            self.api_url,
            headers={"Accept": "application/json"},
        )
        data = resp.json()

        # First element is metadata, skip it
        entries = data[1:] if isinstance(data, list) and len(data) > 1 else []

        kw_lower = {kw.lower() for kw in keywords}
        jobs: list[JobListing] = []
        for entry in entries:
            if not self._matches_keywords(entry, kw_lower):
                continue
            jobs.append(self._parse_entry(entry))
        return jobs

    def _matches_keywords(self, entry: dict, keywords: set[str]) -> bool:
        searchable = " ".join(
            [
                entry.get("position", ""),
                entry.get("company", ""),
                entry.get("description", ""),
                entry.get("location", ""),
                " ".join(entry.get("tags", [])),
            ]
        ).lower()
        return any(kw in searchable for kw in keywords)

    def _parse_entry(self, entry: dict) -> JobListing:
        posted = None
        if epoch := entry.get("epoch"):
            try:
                posted = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
            except (ValueError, TypeError):
                pass

        salary_parts = []
        if smin := entry.get("salary_min"):
            salary_parts.append(str(smin))
        if smax := entry.get("salary_max"):
            salary_parts.append(str(smax))
        salary = " – ".join(salary_parts) if salary_parts else None

        return JobListing(
            title=entry.get("position", "Unknown"),
            company=entry.get("company", "Unknown"),
            url=entry.get("url", f"https://remoteok.com/remote-jobs/{entry.get('id', '')}"),
            source=self.source,
            location=entry.get("location", "Remote"),
            salary=salary,
            description=entry.get("description", ""),
            tags=entry.get("tags", []),
            posted_date=posted,
            remote_type="fully_remote",
        )
