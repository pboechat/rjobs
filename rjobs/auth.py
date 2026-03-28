from __future__ import annotations

import logging

import httpx

from rjobs.config import Credentials

logger = logging.getLogger(__name__)


def has_credentials(creds: Credentials) -> bool:
    return bool(creds.email and creds.password)


async def google_sso_login(
    client: httpx.AsyncClient,
    site_login_url: str,
    google_creds: Credentials,
) -> bool:
    """Attempt Google SSO login via HTTP.

    This is best-effort - many sites enforce CAPTCHA or JS challenges
    that prevent automated HTTP-based login. Falls back gracefully.
    """
    if not has_credentials(google_creds):
        return False

    logger.info("Attempting Google SSO login at %s", site_login_url)
    try:
        resp = await client.get(site_login_url, follow_redirects=True)
        if "accounts.google.com" not in str(resp.url):
            logger.warning("SSO redirect did not reach Google - site may require browser auth")
            return False

        logger.warning(
            "Google SSO via HTTP is unreliable due to bot detection. "
            "Provide session cookies in ~/.config/rjobs/cookies/ instead - "
            "run 'rjobs --init-cookies' for setup instructions."
        )
        return False
    except Exception as e:
        logger.error("Google SSO attempt failed: %s", e)
        return False


async def session_login(
    client: httpx.AsyncClient,
    login_url: str,
    creds: Credentials,
    email_field: str = "email",
    password_field: str = "password",
) -> bool:
    """Attempt direct email/password login via form POST."""
    if not has_credentials(creds):
        return False

    logger.info("Attempting session login at %s", login_url)
    try:
        resp = await client.post(
            login_url,
            data={email_field: creds.email, password_field: creds.password},
            follow_redirects=True,
        )
        if resp.status_code < 400:
            logger.info("Session login succeeded (status %d)", resp.status_code)
            return True
        logger.warning("Session login returned status %d", resp.status_code)
        return False
    except Exception as e:
        logger.error("Session login failed: %s", e)
        return False


# Per-site cookie instructions: login URL and site-specific tips.
COOKIE_HELP: dict[str, dict[str, str]] = {
    "linkedin": {
        "login_url": "https://www.linkedin.com/login",
        "tip": "Log in to LinkedIn, then copy cookies from a request to www.linkedin.com.",
    },
    "glassdoor": {
        "login_url": "https://www.glassdoor.com/profile/login_input.htm",
        "tip": "Log in to Glassdoor, then copy cookies from a request to www.glassdoor.com.",
    },
    "otta": {
        "login_url": "https://app.otta.com/login",
        "tip": "Log in to Otta, then copy cookies from a request to app.otta.com.",
    },
    "wellfound": {
        "login_url": "https://wellfound.com/login",
        "tip": "Log in to Wellfound, then copy cookies from a request to wellfound.com.",
    },
}


def cookie_help_message(site: str) -> str:
    """Return a user-friendly message explaining how to export cookies for *site*."""
    info = COOKIE_HELP.get(site, {})
    login_url = info.get("login_url", "the site")
    tip = info.get("tip", "")
    return (
        f"To use {site} scraping, export your browser cookies:\n"
        f"  1. Open Chrome and go to {login_url}\n"
        f"  2. Log in with your account\n"
        f"  3. Press F12 to open DevTools -> Network tab\n"
        f"  4. Refresh the page (F5)\n"
        f"  5. Click any request to the site's domain\n"
        f"  6. Under 'Headers', copy the full 'Cookie' value\n"
        f"  7. Paste it into ~/.config/rjobs/cookies/{site}\n"
        f"  Tip: {tip}" if tip else ""
    )


def apply_cookies(client: httpx.AsyncClient, cookie_string: str, domain: str) -> None:
    """Inject browser-exported cookies into the HTTP client."""
    if not cookie_string.strip():
        return
    for pair in cookie_string.split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, _, value = pair.partition("=")
            client.cookies.set(name.strip(), value.strip(), domain=domain)
    logger.info("Applied session cookies for %s", domain)
