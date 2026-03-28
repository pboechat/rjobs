from __future__ import annotations

from rjobs.auth import (
    apply_cookies,
    cookie_help_message,
    google_sso_login,
    has_credentials,
)
from rjobs.models import JobListing, Source
from rjobs.scrapers.base import BaseScraper


class OttaScraper(BaseScraper):
    source = Source.OTTA
    base_url = "https://app.otta.com"
    requires_auth = True

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        if not await self._authenticate():
            self.logger.warning("Skipping Otta - authentication required")
            return []

        jobs: list[JobListing] = []
        for kw in keywords:
            try:
                resp = await self._post(
                    f"{self.base_url}/api/search",
                    json={"query": kw, "remote": True, "limit": 50},
                )
                data = resp.json()
                for entry in data.get("results", data.get("jobs", [])):
                    jobs.append(self._parse_entry(entry))
            except Exception as e:
                self.logger.debug("Otta search for '%s' failed: %s", kw, e)
        return jobs

    async def _authenticate(self) -> bool:
        cookie = self.config.credentials.cookies.otta
        if cookie:
            apply_cookies(self.client, cookie, "app.otta.com")
            return True

        google_creds = self.config.credentials.google
        if has_credentials(google_creds):
            return await google_sso_login(
                self.client,
                f"{self.base_url}/login/google",
                google_creds,
            )

        otta_creds = self.config.credentials.otta
        if has_credentials(otta_creds):
            try:
                resp = await self.client.post(
                    f"{self.base_url}/api/auth/login",
                    json={"email": otta_creds.email, "password": otta_creds.password},
                )
                if resp.status_code < 400:
                    return True
                self.logger.warning(
                    "Otta login failed (status %d). %s",
                    resp.status_code,
                    cookie_help_message("otta"),
                )
                return False
            except Exception as e:
                self.logger.error("Otta login failed: %s", e)

        self.logger.warning(
            "Skipping Otta - no credentials or cookies. %s",
            cookie_help_message("otta"),
        )
        return False

    def _parse_entry(self, entry: dict) -> JobListing:
        company = entry.get("company", {})
        salary_raw = entry.get("salary", {})
        salary = None
        if salary_raw and isinstance(salary_raw, dict):
            parts = [str(salary_raw.get("min", "")), str(salary_raw.get("max", ""))]
            salary = " – ".join(p for p in parts if p)

        slug = entry.get("slug", entry.get("id", ""))
        return JobListing(
            title=entry.get("title", "Unknown"),
            company=company.get("name", "Unknown") if isinstance(company, dict) else str(company),
            url=f"https://app.otta.com/jobs/{slug}",
            source=self.source,
            location=entry.get("location", "Remote"),
            salary=salary,
            description=entry.get("description", ""),
            tags=entry.get("tags", []),
        )
