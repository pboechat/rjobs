from __future__ import annotations

from datetime import datetime

from rjobs.models import JobListing, Source
from rjobs.scrapers.base import BaseScraper


class HimalayasScraper(BaseScraper):
    source = Source.HIMALAYAS
    api_url = "https://himalayas.app/jobs/api"

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        jobs: list[JobListing] = []
        seen_ids: set[str] = set()

        for kw in keywords:
            self.logger.debug("GET %s?q=%s", self.api_url, kw)
            resp = await self._get(
                self.api_url,
                params={"q": kw, "limit": 50, "offset": 0},
            )
            data = resp.json()

            for entry in data.get("jobs", []):
                jid = str(entry.get("id", ""))
                if jid in seen_ids:
                    continue
                seen_ids.add(jid)
                jobs.append(self._parse_entry(entry))
        return jobs

    def _parse_entry(self, entry: dict) -> JobListing:
        posted = None
        if pub := entry.get("pubDate", entry.get("publishedAt")):
            try:
                posted = datetime.fromisoformat(str(pub).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        salary = None
        smin = entry.get("salaryCurrencyMin") or entry.get("salaryMin")
        smax = entry.get("salaryCurrencyMax") or entry.get("salaryMax")
        if smin or smax:
            salary = f"{smin or '?'} – {smax or '?'}"

        slug = entry.get("slug", entry.get("id", ""))
        return JobListing(
            title=entry.get("title", "Unknown"),
            company=entry.get("companyName", "Unknown"),
            url=f"https://himalayas.app/jobs/{slug}",
            source=self.source,
            location=entry.get("location", "Remote"),
            salary=salary,
            description=entry.get("description", entry.get("excerpt", "")),
            tags=entry.get("categories", []),
            posted_date=posted,
            remote_type="fully_remote",
        )
