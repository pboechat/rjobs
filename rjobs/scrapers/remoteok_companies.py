from __future__ import annotations

from bs4 import BeautifulSoup

from rjobs.models import JobListing, Source
from rjobs.scrapers.base import BaseScraper


class RemoteOKCompaniesScraper(BaseScraper):
    source = Source.REMOTEOK_COMPANIES
    base_url = "https://remoteok.com/remote-companies"

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        self.logger.debug("GET %s", self.base_url)
        resp = await self._get(self.base_url)
        return self._parse(resp.text, keywords)

    def _parse(self, html: str, keywords: list[str]) -> list[JobListing]:
        soup = BeautifulSoup(html, "lxml")
        kw_lower = {kw.lower() for kw in keywords}
        jobs: list[JobListing] = []

        for row in soup.select("tr.company, div.company"):
            name_el = row.select_one("h2, h3, .company-name, td:first-child a")
            if not name_el:
                continue

            company_name = name_el.get_text(strip=True)
            link = row.select_one("a[href]")
            href = link.get("href", "") if link else ""
            url = href if href.startswith("http") else f"https://remoteok.com{href}"

            location_el = row.select_one(".location, .company-location")
            location = location_el.get_text(strip=True) if location_el else "Remote"

            tags_el = row.select(".tag, .company-tag")
            tags = [t.get_text(strip=True) for t in tags_el]

            searchable = f"{company_name} {location} {' '.join(tags)}".lower()
            if not any(kw in searchable for kw in kw_lower):
                continue

            jobs.append(
                JobListing(
                    title=f"{company_name} - Remote company",
                    company=company_name,
                    url=url,
                    source=self.source,
                    location=location,
                    tags=["company_directory"] + tags,
                    remote_type="fully_remote",
                )
            )

        return jobs
