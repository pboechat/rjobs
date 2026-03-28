from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from rjobs.auth import (
    apply_cookies,
    cookie_help_message,
    has_credentials,
    session_login,
)
from rjobs.models import JobListing, Source
from rjobs.scrapers.base import BaseScraper


class LinkedInScraper(BaseScraper):
    source = Source.LINKEDIN
    base_url = "https://www.linkedin.com"
    requires_auth = True

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        await self._try_auth()
        jobs: list[JobListing] = []
        seen_urls: set[str] = set()

        for kw in keywords:
            # f_WT=2 filters for remote jobs
            url = (
                f"{self.base_url}/jobs-guest/jobs/api/seeMoreJobPostings/search"
                f"?keywords={quote_plus(kw)}&f_WT=2&start=0"
            )
            self.logger.debug("GET %s", url)
            try:
                resp = await self._get(url)
                for job in self._parse(resp.text):
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        jobs.append(job)
            except Exception as e:
                self.logger.debug("LinkedIn search '%s' failed: %s", kw, e)
        return jobs

    async def _try_auth(self) -> None:
        cookie = self.config.credentials.cookies.linkedin
        if cookie:
            apply_cookies(self.client, cookie, "www.linkedin.com")
            return

        creds = self.config.credentials.linkedin
        if has_credentials(creds):
            ok = await session_login(
                self.client,
                f"{self.base_url}/uas/login-submit",
                creds,
                email_field="session_key",
                password_field="session_password",
            )
            if not ok:
                self.logger.warning(
                    "LinkedIn login failed. %s", cookie_help_message("linkedin")
                )
            return

        self.logger.warning(
            "No LinkedIn credentials or cookies configured. %s",
            cookie_help_message("linkedin"),
        )

    def _parse(self, html: str) -> list[JobListing]:
        soup = BeautifulSoup(html, "lxml")
        jobs: list[JobListing] = []

        for card in soup.select("li, div.base-card"):
            title_el = card.select_one("h3.base-search-card__title, .job-search-card__title")
            company_el = card.select_one(
                "h4.base-search-card__subtitle, .job-search-card__subtitle"
            )
            location_el = card.select_one(".job-search-card__location, .base-search-card__metadata")
            link = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")

            if not title_el or not link:
                continue

            href = link.get("href", "")
            # Strip tracking params
            url = href.split("?")[0] if href else ""

            jobs.append(
                JobListing(
                    title=title_el.get_text(strip=True),
                    company=company_el.get_text(strip=True) if company_el else "Unknown",
                    url=url,
                    source=self.source,
                    location=location_el.get_text(strip=True) if location_el else "Remote",
                )
            )

        return jobs
        return jobs
