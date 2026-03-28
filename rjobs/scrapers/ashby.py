from __future__ import annotations

from rjobs.models import JobListing, Source
from rjobs.scrapers.base import BaseScraper


class AshbyScraper(BaseScraper):
    source = Source.ASHBY
    api_url = "https://jobs.ashbyhq.com/api/non-user-graphql"

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        companies = self.config.sources.ats_companies.ashby
        if not companies:
            self.logger.info("No Ashby company slugs configured - skipping")
            return []

        kw_lower = {kw.lower() for kw in keywords}
        jobs: list[JobListing] = []

        for company in companies:
            self.logger.debug("Querying Ashby board: %s", company)
            try:
                resp = await self._post(
                    self.api_url,
                    json={
                        "operationName": "ApiJobBoardWithTeams",
                        "variables": {"organizationHostedJobsPageName": company},
                        "query": ASHBY_QUERY,
                    },
                )
                data = resp.json()
                board = data.get("data", {}).get("jobBoard", {})

                for posting in board.get("jobPostings", []):
                    if self._matches(posting, kw_lower):
                        jobs.append(self._parse_posting(posting, company))
            except Exception as e:
                self.logger.debug("Ashby board '%s' failed: %s", company, e)

        return jobs

    def _matches(self, posting: dict, keywords: set[str]) -> bool:
        searchable = " ".join(
            [
                posting.get("title", ""),
                posting.get("departmentName", ""),
            ]
        ).lower()
        return any(kw in searchable for kw in keywords)

    def _parse_posting(self, posting: dict, company: str) -> JobListing:
        pid = posting.get("id", "")
        return JobListing(
            title=posting.get("title", "Unknown"),
            company=company,
            url=f"https://jobs.ashbyhq.com/{company}/{pid}",
            source=self.source,
            location=posting.get("locationName", "Remote"),
            description=posting.get("descriptionPlain", ""),
            tags=[posting.get("departmentName", "")],
        )


ASHBY_QUERY = """
query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobBoard: jobBoardWithTeams(
    organizationHostedJobsPageName: $organizationHostedJobsPageName
  ) {
    jobPostings {
      id
      title
      locationName
      departmentName
      descriptionPlain
      isRemote
      employmentType
      compensationTierSummary
    }
  }
}
"""
