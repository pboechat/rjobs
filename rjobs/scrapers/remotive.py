from __future__ import annotations

from datetime import datetime

from rjobs.models import JobListing, Source
from rjobs.scrapers.base import BaseScraper


class RemotiveScraper(BaseScraper):
    source = Source.REMOTIVE
    api_url = "https://remotive.com/api/remote-jobs"

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        jobs: list[JobListing] = []
        seen_ids: set[int] = set()

        for kw in keywords:
            self.logger.debug("GET %s?search=%s", self.api_url, kw)
            resp = await self._get(self.api_url, params={"search": kw, "limit": 50})
            data = resp.json()

            for entry in data.get("jobs", []):
                jid = entry.get("id")
                if jid in seen_ids:
                    continue
                seen_ids.add(jid)
                jobs.append(self._parse_entry(entry))
        return jobs

    def _parse_entry(self, entry: dict) -> JobListing:
        posted = None
        if pub := entry.get("publication_date"):
            try:
                posted = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return JobListing(
            title=entry.get("title", "Unknown"),
            company=entry.get("company_name", "Unknown"),
            url=entry.get("url", ""),
            source=self.source,
            location=entry.get("candidate_required_location", "Remote"),
            salary=entry.get("salary") or None,
            description=entry.get("description", ""),
            tags=entry.get("tags", []),
            posted_date=posted,
            remote_type="fully_remote",
        )
