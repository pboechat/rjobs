from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from remote_job_scraper.auth import (
    apply_cookies,
    cookie_help_message,
    has_credentials,
    session_login,
)
from remote_job_scraper.models import JobListing, Source
from remote_job_scraper.scrapers.base import BaseScraper


class GlassdoorScraper(BaseScraper):
    source = Source.GLASSDOOR
    base_url = "https://www.glassdoor.com"
    requires_auth = True

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        if not await self._authenticate():
            self.logger.warning("Skipping Glassdoor - authentication required")
            return []

        jobs: list[JobListing] = []
        seen_urls: set[str] = set()

        for kw in keywords:
            url = f"{self.base_url}/Job/remote-{quote_plus(kw)}-jobs-SRCH_IL.0,6_IS11047_KO7,{7 + len(kw)}.htm"
            self.logger.debug("GET %s", url)
            try:
                resp = await self._get(url)
                for job in self._parse(resp.text):
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        jobs.append(job)
            except Exception as e:
                self.logger.debug("Glassdoor search '%s' failed: %s", kw, e)
        return jobs

    async def _authenticate(self) -> bool:
        cookie = self.config.credentials.cookies.glassdoor
        if cookie:
            apply_cookies(self.client, cookie, "www.glassdoor.com")
            return True

        creds = self.config.credentials.glassdoor
        if has_credentials(creds):
            ok = await session_login(
                self.client,
                f"{self.base_url}/profile/login_input.htm",
                creds,
                email_field="username",
                password_field="password",
            )
            if not ok:
                self.logger.warning(
                    "Glassdoor login failed. %s", cookie_help_message("glassdoor")
                )
            return ok

        self.logger.warning(
            "Skipping Glassdoor - no credentials or cookies. %s",
            cookie_help_message("glassdoor"),
        )
        return False

    def _parse(self, html: str) -> list[JobListing]:
        soup = BeautifulSoup(html, "lxml")
        jobs: list[JobListing] = []

        for card in soup.select(
            "li.react-job-listing, div[data-test='jobListing'], li[data-test='jobListing']"
        ):
            title_el = card.select_one("a.job-title, a[data-test='job-title'], .jobTitle")
            company_el = card.select_one(
                ".job-employer, .employerName, [data-test='employer-short-name']"
            )
            location_el = card.select_one(".job-location, .location, [data-test='emp-location']")
            salary_el = card.select_one(".salary-estimate, [data-test='detailSalary']")

            if not title_el:
                continue

            href = title_el.get("href", "")
            url = href if href.startswith("http") else f"{self.base_url}{href}"

            jobs.append(
                JobListing(
                    title=title_el.get_text(strip=True),
                    company=company_el.get_text(strip=True) if company_el else "Unknown",
                    url=url,
                    source=self.source,
                    location=location_el.get_text(strip=True) if location_el else "Remote",
                    salary=salary_el.get_text(strip=True) if salary_el else None,
                )
            )

        return jobs
        return jobs
