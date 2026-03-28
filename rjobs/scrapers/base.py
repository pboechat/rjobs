from __future__ import annotations

import abc
import asyncio
import logging
from typing import TYPE_CHECKING

import httpx

from rjobs.models import JobListing, Source

if TYPE_CHECKING:
    from rjobs.config import Config

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_RETRIES = 2
RETRY_BACKOFF = 2.0


class BaseScraper(abc.ABC):
    """Base class for all job scrapers."""

    def __init__(self, config: Config, client: httpx.AsyncClient) -> None:
        self.config = config
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    @abc.abstractmethod
    def source(self) -> Source: ...

    @property
    def requires_auth(self) -> bool:
        return False

    @abc.abstractmethod
    async def scrape(self, keywords: list[str]) -> list[JobListing]: ...

    async def search(self, keywords: list[str]) -> list[JobListing]:
        self.logger.info("Starting search on %s", self.source.value)
        try:
            results = await self.scrape(keywords)
            self.logger.info("Found %d listings from %s", len(results), self.source.value)
            return results
        except Exception as e:
            self.logger.error("Scraper %s failed: %s", self.source.value, e)
            return []

    async def _get(self, url: str, **kwargs) -> httpx.Response:
        """GET with retry on transient errors."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self.client.get(url, **kwargs)
                if resp.status_code == 429:
                    wait = RETRY_BACKOFF * (attempt + 1)
                    self.logger.warning("Rate-limited on %s, retrying in %.1fs", url, wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                    continue
                raise
        raise httpx.HTTPStatusError(
            "Max retries exceeded", request=httpx.Request("GET", url), response=resp
        )

    async def _post(self, url: str, **kwargs) -> httpx.Response:
        """POST with retry on transient errors."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self.client.post(url, **kwargs)
                if resp.status_code == 429:
                    wait = RETRY_BACKOFF * (attempt + 1)
                    self.logger.warning("Rate-limited on %s, retrying in %.1fs", url, wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
                    continue
                raise
        raise httpx.HTTPStatusError(
            "Max retries exceeded", request=httpx.Request("POST", url), response=resp
        )
