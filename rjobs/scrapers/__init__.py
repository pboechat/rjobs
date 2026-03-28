from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from rjobs.scrapers.ashby import AshbyScraper
from rjobs.scrapers.base import DEFAULT_HEADERS, BaseScraper
from rjobs.scrapers.github_remote import GitHubRemoteScraper
from rjobs.scrapers.glassdoor import GlassdoorScraper
from rjobs.scrapers.greenhouse import GreenhouseScraper
from rjobs.scrapers.himalayas import HimalayasScraper
from rjobs.scrapers.himalayas_companies import HimalayasCompaniesScraper
from rjobs.scrapers.hn_whoishiring import HNWhoIsHiringScraper
from rjobs.scrapers.indeed import IndeedScraper
from rjobs.scrapers.jobspresso import JobspressoScraper
from rjobs.scrapers.lever import LeverScraper
from rjobs.scrapers.linkedin import LinkedInScraper
from rjobs.scrapers.otta import OttaScraper
from rjobs.scrapers.remoteok import RemoteOKScraper
from rjobs.scrapers.remoteok_companies import RemoteOKCompaniesScraper
from rjobs.scrapers.remotive import RemotiveScraper
from rjobs.scrapers.wellfound import WellfoundScraper
from rjobs.scrapers.weworkremotely import WeWorkRemotelyScraper

if TYPE_CHECKING:
    from rjobs.config import Config

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
