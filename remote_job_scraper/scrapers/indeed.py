from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from remote_job_scraper.models import JobListing, Source
from remote_job_scraper.scrapers.base import BaseScraper

REMOTE_ATTR = "032b3046-06a3-4876-8dfd-474eb5e7ed11"


class IndeedScraper(BaseScraper):
    source = Source.INDEED
    base_url = "https://www.indeed.com"

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        jobs: list[JobListing] = []
        seen_urls: set[str] = set()

        for kw in keywords:
            url = (
                f"{self.base_url}/jobs"
                f"?q={quote_plus(kw)}&l=remote&remotejob={REMOTE_ATTR}&start=0"
            )
            self.logger.debug("GET %s", url)
            try:
                resp = await self._get(url)
                for job in self._parse(resp.text):
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        jobs.append(job)
            except Exception as e:
                self.logger.debug("Indeed search '%s' failed: %s", kw, e)
        return jobs

    def _parse(self, html: str) -> list[JobListing]:
        soup = BeautifulSoup(html, "lxml")
        jobs: list[JobListing] = []

        for card in soup.select("div.job_seen_beacon, div.jobsearch-ResultsList > div"):
            title_el = card.select_one("h2.jobTitle a, a.jcs-JobTitle, [data-testid='jobTitle']")
            company_el = card.select_one("span.companyName, [data-testid='company-name'], .company")
            location_el = card.select_one("div.companyLocation, [data-testid='text-location']")
            salary_el = card.select_one(
                "div.salary-snippet-container, .estimated-salary, .salaryText"
            )
            snippet_el = card.select_one("div.job-snippet, .job-snippet")

            if not title_el:
                continue

            href = title_el.get("href", "")
            if href and not href.startswith("http"):
                href = f"{self.base_url}{href}"

            jobs.append(
                JobListing(
                    title=title_el.get_text(strip=True),
                    company=company_el.get_text(strip=True) if company_el else "Unknown",
                    url=href,
                    source=self.source,
                    location=location_el.get_text(strip=True) if location_el else "Remote",
                    salary=salary_el.get_text(strip=True) if salary_el else None,
                    description=snippet_el.get_text(strip=True) if snippet_el else "",
                )
            )

        return jobs
