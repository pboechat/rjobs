from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Source(str, Enum):
    WEWORKREMOTELY = "weworkremotely"
    REMOTEOK = "remoteok"
    REMOTIVE = "remotive"
    JOBSPRESSO = "jobspresso"
    OTTA = "otta"
    WELLFOUND = "wellfound"
    HIMALAYAS = "himalayas"
    HN_WHOISHIRING = "hn_whoishiring"
    REMOTEOK_COMPANIES = "remoteok_companies"
    HIMALAYAS_COMPANIES = "himalayas_companies"
    GITHUB_REMOTE = "github_remote"
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    GLASSDOOR = "glassdoor"
    ASHBY = "ashby"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"


@dataclass
class JobListing:
    title: str
    company: str
    url: str
    source: Source
    location: str | None = None
    salary: str | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    posted_date: datetime | None = None
    remote_type: str | None = None
    rank: float | None = None
    rank_reasoning: str | None = None

    @property
    def dedup_key(self) -> str:
        title = self.title.lower().strip()
        company = self.company.lower().strip()
        return f"{title}|{company}"
