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

# Patterns that indicate a pipe-field is a location, not a job title.
_LOCATION_INDICATORS = re.compile(
    r"(?i)"
    r"(?:^(?:remote|onsite|on-site|hybrid|full[- ]?time|part[- ]?time|contract)\b)"
    r"|(?:\b(?:remote|onsite|on-site)\b)"
    r"|(?:,\s*(?:CA|NY|MA|TX|WA|OR|IL|CO|NC|VA|GA|FL|PA|OH|UK|US|USA|EU)\b)"
    r"|(?:^[A-Z][\w\s]*,\s*[A-Z]{2,}$)"  # "City, ST" pattern
    r"|(?:\b(?:San Francisco|New York|NYC|Boston|Austin|Seattle|Chicago|"
    r"London|Berlin|Toronto|Paris|Singapore|India|Europe|"
    r"North America|South America|LATAM|EMEA|APAC)\b)"
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

        # Skip short comments or comments that are clearly meta-discussion
        # (no URL and no pipe-separated header = not a real job post)
        clean = re.sub(r"<[^>]+>", "\n", text).strip()
        lines = [ln.strip() for ln in clean.split("\n") if ln.strip()]
        if not lines:
            return None

        header = lines[0]
        has_pipes = "|" in header
        has_url = bool(URL_PATTERN.search(clean))

        # Real job posts almost always have a pipe-delimited header or a URL.
        # Comments without either are meta-discussion or noise.
        if not has_pipes and not has_url:
            return None

        # Require at least 2 pipe-separated fields for a valid header;
        # otherwise the "title" would just be the entire first line.
        parts = PIPE_PATTERN.split(header) if has_pipes else []
        if has_pipes and len(parts) < 2:
            return None

        text_lower = text.lower()
        if not any(kw in text_lower for kw in keywords):
            return None

        return self._extract_job(text, comment_id, data.get("time"), lines, parts)

    def _extract_job(
        self,
        text: str,
        comment_id: int,
        timestamp: int | None,
        lines: list[str],
        parts: list[str],
    ) -> JobListing:
        clean = "\n".join(lines)

        company, title, location = self._classify_header_parts(parts, clean)

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

    @staticmethod
    def _is_location_like(s: str) -> bool:
        """Return True if *s* looks like a location or employment type, not a role."""
        return bool(_LOCATION_INDICATORS.search(s))

    @staticmethod
    def _is_url_like(s: str) -> bool:
        return s.startswith(("http://", "https://", "www."))

    def _classify_header_parts(
        self, parts: list[str], body: str
    ) -> tuple[str, str, str | None]:
        """Classify pipe-separated header fields into (company, title, location).

        HN posts use several formats:
          A) Company | Role | Location | ...       (ideal)
          B) Company | Location | Type | ...       (no role in header)
          C) URL\\n| Location | Role | ...          (URL-first, pipes in body)
          D) Company | Role                        (no location)
        """
        if not parts:
            return ("Unknown", "HN Job Post", None)

        # Filter out parts that are just URLs
        cleaned = [p.strip() for p in parts if not HNWhoIsHiringScraper._is_url_like(p.strip())]
        if not cleaned:
            return ("Unknown", "HN Job Post", None)

        company = cleaned[0]

        if len(cleaned) == 1:
            return (company, "HN Job Post", None)

        # If parts[1] looks like a location/employment-type, the header is
        # format B (Company | Location | ...) rather than A (Company | Role | Location).
        if self._is_location_like(cleaned[1]):
            # Try to find the role in remaining parts
            title = None
            location = cleaned[1]
            for p in cleaned[2:]:
                if not self._is_location_like(p) and not SALARY_PATTERN.search(p):
                    title = p
                    break
            return (company, title or "HN Job Post", location)

        # Standard format A: Company | Role | Location | ...
        title = cleaned[1]
        location = cleaned[2] if len(cleaned) >= 3 else None
        return (company, title, location)
