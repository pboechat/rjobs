from __future__ import annotations

import re
from datetime import datetime, timezone

from rjobs.models import JobListing, Source
from rjobs.scrapers.base import BaseScraper

# Regex to parse HN "Who is Hiring" comment headers
# Typical format: "Company Name | Role | Location | Salary | URL"
PIPE_PATTERN = re.compile(r"\s*\|\s*")
URL_PATTERN = re.compile(r"https?://\S+")
SALARY_PATTERN = re.compile(
    r"\$[\d,]+(?:\s*[-–]\s*\$?[\d,]+)?|[\d]+k\s*[-–]\s*[\d]+k", re.IGNORECASE
)


class HNWhoIsHiringScraper(BaseScraper):
    source = Source.HN_WHOISHIRING
    algolia_url = "https://hn.algolia.com/api/v1/search"
    hn_item_url = "https://hacker-news.firebaseio.com/v0/item"

    async def scrape(self, keywords: list[str]) -> list[JobListing]:
        story_id = await self._find_latest_thread()
        if not story_id:
            self.logger.warning("Could not find latest Who is Hiring thread")
            return []

        self.logger.info("Fetching HN thread %s", story_id)
        comment_ids = await self._get_child_ids(story_id)
        kw_lower = {kw.lower() for kw in keywords}

        jobs: list[JobListing] = []
        for cid in comment_ids[:300]:  # cap to avoid excessive API calls
            job = await self._parse_comment(cid, kw_lower)
            if job:
                jobs.append(job)
        return jobs

    async def _find_latest_thread(self) -> int | None:
        resp = await self._get(
            self.algolia_url,
            params={
                "query": "Ask HN: Who is hiring",
                "tags": "story,author_whoishiring",
                "hitsPerPage": 1,
            },
        )
        data = resp.json()
        hits = data.get("hits", [])
        if not hits:
            return None
        return int(hits[0]["objectID"])

    async def _get_child_ids(self, story_id: int) -> list[int]:
        resp = await self._get(f"{self.hn_item_url}/{story_id}.json")
        data = resp.json()
        return data.get("kids", [])

    async def _parse_comment(self, comment_id: int, keywords: set[str]) -> JobListing | None:
        try:
            resp = await self._get(f"{self.hn_item_url}/{comment_id}.json")
            data = resp.json()
        except Exception:
            return None

        if not data or data.get("deleted") or data.get("dead"):
            return None

        text = data.get("text", "")
        text_lower = text.lower()

        if not any(kw in text_lower for kw in keywords):
            return None

        return self._extract_job(text, comment_id, data.get("time"))

    def _extract_job(self, text: str, comment_id: int, timestamp: int | None) -> JobListing:
        # Strip HTML tags for plain-text parsing
        clean = re.sub(r"<[^>]+>", "\n", text).strip()
        lines = [ln.strip() for ln in clean.split("\n") if ln.strip()]

        # First line is usually "Company | Role | Location | ..."
        header = lines[0] if lines else ""
        parts = PIPE_PATTERN.split(header)

        company = parts[0].strip() if len(parts) >= 1 else "Unknown"
        title = parts[1].strip() if len(parts) >= 2 else header
        location = parts[2].strip() if len(parts) >= 3 else None

        salary_match = SALARY_PATTERN.search(clean)
        salary = salary_match.group(0) if salary_match else None

        url_match = URL_PATTERN.search(clean)
        job_url = (
            url_match.group(0)
            if url_match
            else f"https://news.ycombinator.com/item?id={comment_id}"
        )

        posted = None
        if timestamp:
            posted = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        description = "\n".join(lines[1:])[:1000]

        return JobListing(
            title=title or "HN Job Post",
            company=company,
            url=job_url,
            source=self.source,
            location=location,
            salary=salary,
            description=description,
            posted_date=posted,
        )
