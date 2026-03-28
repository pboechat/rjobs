from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

APP_NAME = "rjobs"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / APP_NAME
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yml"
DEFAULT_COOKIES_DIR = DEFAULT_CONFIG_DIR / "cookies"

DEFAULT_KEYWORDS: list[str] = [
    "remote",
    "worldwide",
    "anywhere",
    "async",
    "global",
    "distributed",
]

DEFAULT_SYSTEM_PROMPT = """\
You are a remote job opportunity evaluator. For each job listing provided, \
assign a numeric rank from 0 to 10 based on the following criteria:
- Remote-friendliness (truly remote vs. remote with geographic restrictions)
- Clarity and completeness of the listing
- Company reputation and stability indicators
- Compensation transparency

Respond ONLY with a JSON object containing a "rankings" key whose value is an array:
{"rankings": [{"index": 0, "rank": 7, "reasoning": "brief reason"}, ...]}
"""

CONFIG_TEMPLATE = """\
# Remote Job Scraper configuration
# Docs: https://github.com/youruser/rjobs

credentials:
  google:
    email: ""
    password: ""
  linkedin:
    email: ""
    password: ""
  glassdoor:
    email: ""
    password: ""
  wellfound:
    email: ""
    password: ""
  otta:
    email: ""
    password: ""
  # Session cookies are stored as individual files under ~/.config/rjobs/cookies/
  # e.g. ~/.config/rjobs/cookies/linkedin, ~/.config/rjobs/cookies/glassdoor
  # Run 'rjobs --init-cookies' to create the cookie directory with empty template files.

llm:
  base_url: "http://localhost:11434/v1"
  api_key: ""
  model: "gpt-4"
  temperature: 0.3
  max_tokens: 4096

search:
  keywords:
    - "remote"
    - "worldwide"
    - "anywhere"
    - "async"
    - "global"
    - "distributed"


sources:
  enabled: []  # empty = all enabled
  ats_companies:
    ashby:
      - "notion"
      - "ramp"
      - "linear"
    greenhouse:
      - "gitlab"
      - "hashicorp"
      - "cloudflare"
    lever:
      - "netflix"
      - "remote-com"

filter:
  remote_only: true  # discard listings whose location lacks remote indicators

ranking:
  threshold: 5
  system_prompt: |
    You are a remote job opportunity evaluator. For each job listing provided,
    assign a numeric rank from 0 to 10 based on:
    - Remote-friendliness (truly remote vs. remote with restrictions)
    - Clarity and completeness of the listing
    - Company reputation and stability indicators
    - Compensation transparency

    Respond ONLY with a JSON object:
    {"rankings": [{"index": 0, "rank": 7, "reasoning": "brief reason"}, ...]}
"""


@dataclass
class Credentials:
    email: str = ""
    password: str = ""


@dataclass
class CookieStore:
    otta: str = ""
    wellfound: str = ""
    linkedin: str = ""
    glassdoor: str = ""


@dataclass
class CredentialsConfig:
    google: Credentials = field(default_factory=Credentials)
    linkedin: Credentials = field(default_factory=Credentials)
    glassdoor: Credentials = field(default_factory=Credentials)
    wellfound: Credentials = field(default_factory=Credentials)
    otta: Credentials = field(default_factory=Credentials)
    cookies: CookieStore = field(default_factory=CookieStore)


@dataclass
class LLMConfig:
    base_url: str = "http://localhost:11434/v1"
    api_key: str = ""
    model: str = "gpt-4"
    temperature: float = 0.3
    max_tokens: int = 4096


@dataclass
class SearchConfig:
    keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))


@dataclass
class ATSCompanies:
    ashby: list[str] = field(default_factory=lambda: ["notion", "ramp", "linear"])
    greenhouse: list[str] = field(default_factory=lambda: ["gitlab", "hashicorp", "cloudflare"])
    lever: list[str] = field(default_factory=lambda: ["netflix", "remote-com"])


@dataclass
class SourcesConfig:
    enabled: list[str] = field(default_factory=list)
    ats_companies: ATSCompanies = field(default_factory=ATSCompanies)


@dataclass
class RankingConfig:
    threshold: int = 5
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


@dataclass
class FilterConfig:
    remote_only: bool = True


@dataclass
class Config:
    credentials: CredentialsConfig = field(default_factory=CredentialsConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    ranking: RankingConfig = field(default_factory=RankingConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)


def _build_credentials(raw: dict) -> Credentials:
    return Credentials(email=raw.get("email", ""), password=raw.get("password", ""))


def _load_cookie(name: str, cookies_dir: Path) -> str:
    """Read a cookie from *cookies_dir*/*name* if it exists."""
    cookie_file = cookies_dir / name
    if cookie_file.is_file():
        lines = cookie_file.read_text().splitlines()
        content = "\n".join(l for l in lines if not l.lstrip().startswith("#")).strip()
        if content:
            logger.debug("Loaded cookie for %s from %s", name, cookie_file)
            return content
    return ""


def _load_cookies(cookies_dir: Path) -> CookieStore:
    """Build a CookieStore from files in *cookies_dir*."""
    return CookieStore(
        otta=_load_cookie("otta", cookies_dir),
        wellfound=_load_cookie("wellfound", cookies_dir),
        linkedin=_load_cookie("linkedin", cookies_dir),
        glassdoor=_load_cookie("glassdoor", cookies_dir),
    )


def _load_config_dict(data: dict, cookies_dir: Path = DEFAULT_COOKIES_DIR) -> Config:
    creds_raw = data.get("credentials", {})
    credentials = CredentialsConfig(
        google=_build_credentials(creds_raw.get("google", {})),
        linkedin=_build_credentials(creds_raw.get("linkedin", {})),
        glassdoor=_build_credentials(creds_raw.get("glassdoor", {})),
        wellfound=_build_credentials(creds_raw.get("wellfound", {})),
        otta=_build_credentials(creds_raw.get("otta", {})),
        cookies=_load_cookies(cookies_dir),
    )

    _llm_defaults = LLMConfig()
    llm_raw = data.get("llm", {})
    llm = LLMConfig(
        base_url=llm_raw.get("base_url", _llm_defaults.base_url),
        api_key=llm_raw.get("api_key", ""),
        model=llm_raw.get("model", _llm_defaults.model),
        temperature=float(llm_raw.get("temperature", _llm_defaults.temperature)),
        max_tokens=int(llm_raw.get("max_tokens", _llm_defaults.max_tokens)),
    )

    search_raw = data.get("search", {})
    search = SearchConfig(
        keywords=search_raw.get("keywords", list(DEFAULT_KEYWORDS)),
    )

    _ats_defaults = ATSCompanies()
    sources_raw = data.get("sources", {})
    ats_raw = sources_raw.get("ats_companies", {})
    sources = SourcesConfig(
        enabled=sources_raw.get("enabled", []),
        ats_companies=ATSCompanies(
            ashby=ats_raw.get("ashby", _ats_defaults.ashby),
            greenhouse=ats_raw.get("greenhouse", _ats_defaults.greenhouse),
            lever=ats_raw.get("lever", _ats_defaults.lever),
        ),
    )

    _ranking_defaults = RankingConfig()
    ranking_raw = data.get("ranking", {})
    ranking = RankingConfig(
        threshold=int(ranking_raw.get("threshold", _ranking_defaults.threshold)),
        system_prompt=ranking_raw.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
    )

    filter_raw = data.get("filter", {})
    filter_cfg = FilterConfig(
        remote_only=filter_raw.get("remote_only", True),
    )

    return Config(
        credentials=credentials,
        llm=llm,
        search=search,
        sources=sources,
        ranking=ranking,
        filter=filter_cfg,
    )


def load_config(path: Path | None = None) -> Config:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        logger.info("No config found at %s - using defaults", config_path)
        return Config()

    logger.info("Loading config from %s", config_path)
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}
    return _load_config_dict(data)


def write_template_config(path: Path | None = None) -> Path:
    config_path = path or DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(CONFIG_TEMPLATE)
    logger.info("Wrote config template to %s", config_path)
    return config_path


COOKIE_FILE_TEMPLATE = """\
# Paste the full Cookie header value from your browser below.
# How to get cookies from Chrome:
#   1. Open Chrome and log in to {login_url}
#   2. Press F12 -> Network tab, then refresh the page (F5)
#   3. Click any request to the site's domain
#   4. Under 'Headers', copy the full 'Cookie' value
#   5. Paste it below (replace this comment block)
"""

_COOKIE_LOGIN_URLS: dict[str, str] = {
    "otta": "https://app.otta.com/login",
    "wellfound": "https://wellfound.com/login",
    "linkedin": "https://www.linkedin.com/login",
    "glassdoor": "https://www.glassdoor.com/profile/login_input.htm",
}


def write_cookie_templates(cookies_dir: Path | None = None) -> Path:
    """Create the cookies directory with empty template files for each site."""
    cdir = cookies_dir or DEFAULT_COOKIES_DIR
    cdir.mkdir(parents=True, exist_ok=True)
    for name, login_url in _COOKIE_LOGIN_URLS.items():
        cookie_file = cdir / name
        if not cookie_file.exists():
            cookie_file.write_text(COOKIE_FILE_TEMPLATE.format(login_url=login_url))
            logger.info("Created cookie template: %s", cookie_file)
        else:
            logger.info("Cookie file already exists, skipping: %s", cookie_file)
    return cdir
