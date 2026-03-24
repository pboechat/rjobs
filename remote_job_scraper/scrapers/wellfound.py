from __future__ import annotations

from remote_job_scraper.auth import (
    apply_cookies,
    cookie_help_message,
    google_sso_login,
    has_credentials,
)
from remote_job_scraper.models import JobListing, Source
from remote_job_scraper.scrapers.base import BaseScraper


class WellfoundScraper(BaseScraper):
    source = Source.WELLFOUND
    base_url = "https://wellfound.com"
    requires_auth = True

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        if not await self._authenticate():
            self.logger.warning("Skipping Wellfound - authentication required")
            return []

        jobs: list[JobListing] = []
        for kw in keywords:
            try:
                resp = await self._post(
                    f"{self.base_url}/api/graphql",
                    json={
                        "query": SEARCH_QUERY,
                        "variables": {"query": kw, "remote": True, "page": 1},
                    },
                )
                data = resp.json()
                edges = data.get("data", {}).get("jobListings", {}).get("edges", [])
                for edge in edges:
                    node = edge.get("node", edge)
                    jobs.append(self._parse_entry(node))
            except Exception as e:
                self.logger.debug("Wellfound search for '%s' failed: %s", kw, e)
        return jobs

    async def _authenticate(self) -> bool:
        cookie = self.config.credentials.cookies.wellfound
        if cookie:
            apply_cookies(self.client, cookie, "wellfound.com")
            return True

        google_creds = self.config.credentials.google
        if has_credentials(google_creds):
            return await google_sso_login(
                self.client,
                f"{self.base_url}/login/google_oauth2",
                google_creds,
            )

        wf_creds = self.config.credentials.wellfound
        if has_credentials(wf_creds):
            try:
                resp = await self.client.post(
                    f"{self.base_url}/api/sessions",
                    json={"user": {"email": wf_creds.email, "password": wf_creds.password}},
                )
                if resp.status_code < 400:
                    return True
                self.logger.warning(
                    "Wellfound login failed (status %d). %s",
                    resp.status_code,
                    cookie_help_message("wellfound"),
                )
                return False
            except Exception as e:
                self.logger.error("Wellfound login failed: %s", e)

        self.logger.warning(
            "Skipping Wellfound - no credentials or cookies. %s",
            cookie_help_message("wellfound"),
        )
        return False

    def _parse_entry(self, entry: dict) -> JobListing:
        startup = entry.get("startup", entry.get("company", {}))
        company_name = startup.get("name", "Unknown") if isinstance(startup, dict) else "Unknown"

        comp = entry.get("compensation")
        salary = None
        if comp:
            salary = f"{comp.get('min', '?')} – {comp.get('max', '?')} {comp.get('currency', '')}"

        slug = entry.get("slug", entry.get("id", ""))
        return JobListing(
            title=entry.get("title", "Unknown"),
            company=company_name,
            url=f"{self.base_url}/jobs/{slug}",
            source=self.source,
            location=entry.get("locationNames", "Remote"),
            salary=salary,
            description=entry.get("description", ""),
            tags=entry.get("roleTypes", []),
        )


SEARCH_QUERY = """
query SearchJobs($query: String!, $remote: Boolean, $page: Int) {
  jobListings(filters: {query: $query, remote: $remote}, page: $page) {
    edges {
      node {
        id
        slug
        title
        description
        locationNames
        compensation { min max currency }
        roleTypes
        startup { name slug }
      }
    }
  }
}
"""
