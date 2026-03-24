from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from remote_job_scraper.scrapers.ashby import AshbyScraper
from remote_job_scraper.scrapers.base import DEFAULT_HEADERS, BaseScraper
from remote_job_scraper.scrapers.github_remote import GitHubRemoteScraper
from remote_job_scraper.scrapers.glassdoor import GlassdoorScraper
from remote_job_scraper.scrapers.greenhouse import GreenhouseScraper
from remote_job_scraper.scrapers.himalayas import HimalayasScraper
from remote_job_scraper.scrapers.himalayas_companies import HimalayasCompaniesScraper
from remote_job_scraper.scrapers.hn_whoishiring import HNWhoIsHiringScraper
from remote_job_scraper.scrapers.indeed import IndeedScraper
from remote_job_scraper.scrapers.jobspresso import JobspressoScraper
from remote_job_scraper.scrapers.lever import LeverScraper
from remote_job_scraper.scrapers.linkedin import LinkedInScraper
from remote_job_scraper.scrapers.otta import OttaScraper
from remote_job_scraper.scrapers.remoteok import RemoteOKScraper
from remote_job_scraper.scrapers.remoteok_companies import RemoteOKCompaniesScraper
from remote_job_scraper.scrapers.remotive import RemotiveScraper
from remote_job_scraper.scrapers.wellfound import WellfoundScraper
from remote_job_scraper.scrapers.weworkremotely import WeWorkRemotelyScraper

if TYPE_CHECKING:
    from remote_job_scraper.config import Config

ALL_SCRAPERS: list[type[BaseScraper]] = [
    WeWorkRemotelyScraper,
    RemoteOKScraper,
    RemotiveScraper,
    JobspressoScraper,
    OttaScraper,
    WellfoundScraper,
    HimalayasScraper,
    HNWhoIsHiringScraper,
    RemoteOKCompaniesScraper,
    HimalayasCompaniesScraper,
    GitHubRemoteScraper,
    LinkedInScraper,
    IndeedScraper,
    GlassdoorScraper,
    AshbyScraper,
    GreenhouseScraper,
    LeverScraper,
]

SOURCE_NAME_MAP: dict[str, type[BaseScraper]] = {cls.__name__: cls for cls in ALL_SCRAPERS}


def get_scrapers(
    config: Config,
    client: httpx.AsyncClient,
    source_filter: list[str] | None = None,
) -> list[BaseScraper]:
    enabled = config.sources.enabled or None
    scrapers: list[BaseScraper] = []

    for cls in ALL_SCRAPERS:
        scraper = cls(config, client)
        name = scraper.source.value

        if source_filter and name not in source_filter:
            continue
        if enabled and name not in enabled:
            continue

        scrapers.append(scraper)

    return scrapers


def build_http_client(timeout: float = 30.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
