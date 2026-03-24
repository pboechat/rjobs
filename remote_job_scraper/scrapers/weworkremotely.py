from __future__ import annotations

from bs4 import BeautifulSoup

from remote_job_scraper.models import JobListing, Source
from remote_job_scraper.scrapers.base import BaseScraper


class WeWorkRemotelyScraper(BaseScraper):
    source = Source.WEWORKREMOTELY
    base_url = "https://weworkremotely.com"

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        # The search endpoint blocks automated requests (403).
        # Fetch the main listing page and filter client-side by keyword.
        url = f"{self.base_url}/remote-jobs"
        self.logger.debug("GET %s", url)
        resp = await self._get(url)
        all_jobs = self._parse(resp.text)

        if not keywords:
            return all_jobs

        kw_lower = [kw.lower() for kw in keywords]
        return [
            job
            for job in all_jobs
            if any(
                kw in job.title.lower() or kw in job.company.lower()
                for kw in kw_lower
            )
        ]

    def _parse(self, html: str) -> list[JobListing]:
        soup = BeautifulSoup(html, "lxml")
        jobs: list[JobListing] = []
        seen_urls: set[str] = set()

        for li in soup.select("li.new-listing-container"):
            link = li.select_one("a.listing-link--unlocked[href*='/remote-jobs/']")
            if not link:
                continue

            title_el = li.select_one(".new-listing__header__title__text, h3.new-listing__header__title")
            company_el = li.select_one(".new-listing__company-name")
            location_el = li.select_one(".new-listing__company-headquarters")

            if not title_el:
                continue

            href = link.get("href", "")
            url = href if href.startswith("http") else f"{self.base_url}{href}"

            if url in seen_urls:
                continue
            seen_urls.add(url)

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
