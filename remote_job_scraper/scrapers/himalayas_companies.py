from __future__ import annotations

from remote_job_scraper.models import JobListing, Source
from remote_job_scraper.scrapers.base import BaseScraper


class HimalayasCompaniesScraper(BaseScraper):
    source = Source.HIMALAYAS_COMPANIES
    api_url = "https://himalayas.app/companies/api"

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        jobs: list[JobListing] = []
        seen: set[str] = set()

        for kw in keywords:
            self.logger.debug("GET %s?q=%s", self.api_url, kw)
            try:
                resp = await self._get(
                    self.api_url,
                    params={"q": kw, "limit": 50, "offset": 0},
                )
                data = resp.json()

                for entry in data.get("companies", []):
                    name = entry.get("name", "")
                    if name in seen:
                        continue
                    seen.add(name)
                    jobs.append(self._parse_entry(entry))
            except Exception as e:
                self.logger.debug("Himalayas companies search '%s' failed: %s", kw, e)
        return jobs

    def _parse_entry(self, entry: dict) -> JobListing:
        slug = entry.get("slug", entry.get("id", ""))
        return JobListing(
            title=f"{entry.get('name', 'Unknown')} - Remote company",
            company=entry.get("name", "Unknown"),
            url=f"https://himalayas.app/companies/{slug}",
            source=self.source,
            location=entry.get("hq", "Various"),
            description=entry.get("description", entry.get("bio", "")),
            tags=["company_directory"] + entry.get("categories", []),
            remote_type="fully_remote",
        )
