from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml
from bs4 import BeautifulSoup
from openai import AsyncOpenAI

from rjobs.auth import cookie_help_message, has_credentials
from rjobs.config import Config

logger = logging.getLogger(__name__)

PROFILE_DIR = Path.home() / ".cache" / "rjobs" / "profiles"
DEFAULT_PROFILE = "default"


def profile_path_for(name: str = DEFAULT_PROFILE) -> Path:
    """Return the on-disk path for a named applicant profile."""
    return PROFILE_DIR / f"{name}.yml"


# Convenience alias used by old imports
PROFILE_PATH = profile_path_for(DEFAULT_PROFILE)

RESUME_DIGEST_PROMPT = """\
You are an expert recruiter and career analyst. Given the text of a resume/CV, \
extract a structured profile of the applicant. Be thorough but concise.

Respond ONLY with a JSON object with these keys:
{
  "name": "Full name",
  "summary": "2-3 sentence professional summary",
  "target_roles": ["list of job titles/roles the person is suited for"],
  "skills": ["list of technical and professional skills"],
  "experience_areas": ["list of domains/industries the person has worked in"],
  "years_of_experience": "approximate total years of professional experience",
  "education": "highest degree and field, institution if notable",
  "preferences": "any stated preferences (remote, location, company size, etc.)",
  "role_keywords": ["short search keywords a job board would understand, e.g. 'backend engineer', 'python developer', 'devops', 'data scientist'. Infer 3-8 keywords from the resume that best capture the roles this person should search for."]
}
"""


@dataclass
class ApplicantProfile:
    name: str = ""
    summary: str = ""
    target_roles: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    experience_areas: list[str] = field(default_factory=list)
    years_of_experience: str = ""
    education: str = ""
    preferences: str = ""
    role_keywords: list[str] = field(default_factory=list)

    def to_ranking_context(self) -> str:
        """Format the profile as context to inject into the ranking prompt."""
        parts = [f"Applicant: {self.name}"] if self.name else []
        if self.summary:
            parts.append(f"Summary: {self.summary}")
        if self.target_roles:
            parts.append(f"Target roles: {', '.join(self.target_roles)}")
        if self.skills:
            parts.append(f"Skills: {', '.join(self.skills)}")
        if self.experience_areas:
            parts.append(f"Experience areas: {', '.join(self.experience_areas)}")
        if self.years_of_experience:
            parts.append(f"Years of experience: {self.years_of_experience}")
        if self.education:
            parts.append(f"Education: {self.education}")
        if self.preferences:
            parts.append(f"Preferences: {self.preferences}")
        if self.role_keywords:
            parts.append(f"Role keywords: {', '.join(self.role_keywords)}")
        return "\n".join(parts)


def load_profile(name: str = DEFAULT_PROFILE) -> ApplicantProfile | None:
    """Load an applicant profile by name, or return None if it doesn't exist.

    Falls back to the legacy ``applicant.yml`` location when the *default*
    profile is requested and no new-style file exists yet.
    """
    path = profile_path_for(name)
    if not path.exists():
        return None
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return ApplicantProfile(**{k: v for k, v in data.items() if k in ApplicantProfile.__dataclass_fields__})


def save_profile(profile: ApplicantProfile, name: str = DEFAULT_PROFILE) -> Path:
    """Save an applicant profile to YAML under the given name."""
    path = profile_path_for(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(asdict(profile), f, default_flow_style=False, sort_keys=False)
    return path


def extract_text_from_file(file_path: Path) -> str:
    """Extract text from a resume file (PDF, markdown, or plain text)."""
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf(file_path)
    elif suffix in (".md", ".markdown", ".txt", ".text", ""):
        return file_path.read_text(encoding="utf-8")
    else:
        # Try reading as plain text
        return file_path.read_text(encoding="utf-8")


def _extract_pdf(file_path: Path) -> str:
    """Extract text from a PDF using PyMuPDF."""
    try:
        import fitz
    except ImportError:
        raise RuntimeError(
            "PyMuPDF is required for PDF parsing. Install it with: pip install pymupdf"
        )

    doc = fitz.open(file_path)
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n\n".join(pages)


LINKEDIN_PROFILE_URL_RE = re.compile(
    r"^https?://(?:www\.)?linkedin\.com/in/[\w-]+/?$"
)


def is_linkedin_profile_url(value: str) -> bool:
    """Return True if *value* looks like a LinkedIn profile URL."""
    return bool(LINKEDIN_PROFILE_URL_RE.match(value.strip().rstrip("/") + "/"))


async def scrape_linkedin_profile(url: str, config: Config) -> str:
    """Scrape a LinkedIn profile page and return its text content.

    Uses Playwright (headless browser) to bypass LinkedIn's bot detection.
    Authenticates via session cookies or email/password from the config.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright is required for LinkedIn profile scraping. "
            "Install it with: pip install playwright && playwright install chromium"
        )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )

        # Inject session cookies if available
        cookie = config.credentials.cookies.linkedin
        if cookie:
            cookies = _parse_cookie_string(cookie, ".linkedin.com")
            if cookies:
                await context.add_cookies(cookies)

        page = await context.new_page()

        # If no cookies, try logging in with credentials
        if not cookie:
            creds = config.credentials.linkedin
            if has_credentials(creds):
                await _playwright_linkedin_login(page, creds)

        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        if resp is None or resp.status >= 400:
            status = resp.status if resp else "no response"
            await browser.close()
            raise RuntimeError(
                f"LinkedIn returned status {status} for {url}. "
                f"{cookie_help_message('linkedin')}"
            )

        # Wait for the profile content to render
        try:
            await page.wait_for_selector(
                "h1, .top-card-layout__title, .text-heading-xlarge",
                timeout=10_000,
            )
        except Exception:
            pass  # proceed with whatever loaded

        html = await page.content()
        await browser.close()

    return _extract_linkedin_profile_text(html)


def _parse_cookie_string(cookie_string: str, domain: str) -> list[dict]:
    """Convert a semicolon-separated cookie string to Playwright cookie dicts."""
    cookies = []
    for pair in cookie_string.split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, _, value = pair.partition("=")
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": domain,
                "path": "/",
            })
    return cookies


async def _playwright_linkedin_login(page, creds) -> None:
    """Log in to LinkedIn using Playwright with email/password."""
    await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
    await page.fill("#username", creds.email)
    await page.fill("#password", creds.password)
    await page.click("button[type='submit']")
    try:
        await page.wait_for_url("**/feed/**", timeout=15_000)
    except Exception:
        logger.warning(
            "LinkedIn login may have hit a CAPTCHA or verification challenge. "
            "%s", cookie_help_message("linkedin"),
        )


def _extract_linkedin_profile_text(html: str) -> str:
    """Extract meaningful text from a LinkedIn profile HTML page."""
    soup = BeautifulSoup(html, "lxml")

    # Remove scripts, styles, and nav elements
    for tag in soup.select("script, style, nav, footer, header, noscript"):
        tag.decompose()

    sections: list[str] = []

    # Try structured selectors commonly found on public/semi-public profiles
    name_el = soup.select_one(
        "h1.text-heading-xlarge, h1.top-card-layout__title, "
        ".pv-text-details--left h1"
    )
    if name_el:
        sections.append(f"Name: {name_el.get_text(strip=True)}")

    headline_el = soup.select_one(
        ".text-body-medium, .top-card-layout__headline, "
        ".pv-text-details--left .text-body-medium"
    )
    if headline_el:
        sections.append(f"Headline: {headline_el.get_text(strip=True)}")

    about_el = soup.select_one(
        "#about ~ .display-flex .pv-shared-text-with-see-more span, "
        "section.summary .description, "
        ".pv-about__summary-text"
    )
    if about_el:
        sections.append(f"About: {about_el.get_text(strip=True)}")

    # Experience, education, skills sections – grab all visible text
    for section in soup.select(
        "section.experience, section.education, section.skills, "
        "#experience, #education, #skills, "
        ".pv-profile-section"
    ):
        text = section.get_text(separator="\n", strip=True)
        if text:
            sections.append(text)

    # If structured extraction gave us enough, use it
    if len(sections) >= 3:
        return "\n\n".join(sections)

    # Fallback: grab all visible text from the page body
    body = soup.find("body")
    if body:
        return body.get_text(separator="\n", strip=True)
    return soup.get_text(separator="\n", strip=True)


async def digest_resume(resume_text: str, config: Config) -> ApplicantProfile:
    """Send resume text to LLM and parse the structured profile response."""
    client = AsyncOpenAI(
        base_url=config.llm.base_url,
        api_key=config.llm.api_key or "not-needed",
    )

    resp = await client.chat.completions.create(
        model=config.llm.model,
        temperature=config.llm.temperature,
        max_tokens=config.llm.max_tokens,
        messages=[
            {"role": "system", "content": RESUME_DIGEST_PROMPT},
            {"role": "user", "content": f"Here is the resume:\n\n{resume_text}"},
        ],
    )

    content = resp.choices[0].message.content or ""

    # Strip markdown code block wrapper if present
    json_str = content.strip()
    if json_str.startswith("```"):
        json_str = "\n".join(json_str.split("\n")[1:])
        if json_str.endswith("```"):
            json_str = json_str[:-3]

    parsed = None
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        # LLM may have included prose around the JSON; try to extract it
        match = re.search(r"\{[\s\S]*\}", json_str)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                pass
    if parsed is None:
        logger.error("Could not parse LLM response as JSON. Raw response:\n%s", content[:1000])
        raise RuntimeError("LLM did not return valid JSON for the resume digest")

    return ApplicantProfile(
        name=parsed.get("name", ""),
        summary=parsed.get("summary", ""),
        target_roles=parsed.get("target_roles", []),
        skills=parsed.get("skills", []),
        experience_areas=parsed.get("experience_areas", []),
        years_of_experience=str(parsed.get("years_of_experience", "")),
        education=parsed.get("education", ""),
        preferences=parsed.get("preferences", ""),
    )
