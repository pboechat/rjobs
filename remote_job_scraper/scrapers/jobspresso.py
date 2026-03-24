from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from remote_job_scraper.models import JobListing, Source
from remote_job_scraper.scrapers.base import BaseScraper


class JobspressoScraper(BaseScraper):
    source = Source.JOBSPRESSO
    base_url = "https://jobspresso.co"
    _ajax_url = f"{base_url}/jm-ajax/get_listings/"

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        jobs: list[JobListing] = []
        seen_urls: set[str] = set()

        for kw in keywords:
            self.logger.debug("POST %s (keyword=%s)", self._ajax_url, kw)
            resp = await self._post(
                self._ajax_url,
                data={
                    "search_keywords": kw,
                    "per_page": 25,
                    "page": 1,
                },
            )
            data = resp.json()
            if not data.get("found_jobs"):
                continue
            for job in self._parse(data.get("html", "")):
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    jobs.append(job)
        return jobs

    def _parse(self, html: str) -> list[JobListing]:
        soup = BeautifulSoup(html, "lxml")
        jobs: list[JobListing] = []

        for li in soup.select("li.job_listing"):
            link = li.select_one("a.job_listing-clickbox[href]")
            if not link:
                continue

            title_el = li.select_one("h3.job_listing-title")
            company_el = li.select_one(".job_listing-company strong")
            location_el = li.select_one(".job_listing-location")

            if not title_el:
                continue

            href = link.get("href", "")
            url = href if href.startswith("http") else f"{self.base_url}{href}"

            jobs.append(
                JobListing(
                    title=title_el.get_text(strip=True),
                    company=company_el.get_text(strip=True) if company_el else "Unknown",
                    url=url,
                    source=self.source,
                    location=location_el.get_text(strip=True) if location_el else "Remote",
                    remote_type="fully_remote",
                )
            )

        return jobs
