# rjobs (Remote Jobs Scraper)

A CLI tool to search and rank remote job opportunities across multiple sources using LLM-powered analysis.

## Table of Contents

- [Features](#features)
- [Sources](#sources)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Applicant Profiles](#applicant-profiles)
- [Configuration](#configuration)
- [CLI Reference](#cli-reference)
- [Authentication Notes](#authentication-notes)
- [Development](#development)

## Features

- **17 sources** - job boards, company directories, ATS platforms, and aggregators
- **Async scraping** - all sources queried in parallel for speed
- **LLM ranking** - jobs ranked 0-10 via any OpenAI-compatible API (local or cloud)
- **Deduplication** - cross-source duplicate removal
- **Flexible Output** - stdout, JSON, or CSV
- **Configurable** - YAML config file with credentials, keywords, and LLM settings

## Sources

| Source | Type | Auth |
|---|---|---|
| [WeWorkRemotely](https://weworkremotely.com/) | Job board | No |
| [RemoteOK](https://remoteok.com/) | Job board (API) | No |
| [Remotive](https://remotive.com/remote-jobs) | Job board (API) | No |
| [Jobspresso](https://jobspresso.co/) | Job board | No |
| [Otta](https://app.otta.com/) | Job board | Google SSO / cookies |
| [Wellfound](https://wellfound.com/jobs) | Job board | Google SSO / cookies |
| [Himalayas](https://himalayas.app/jobs) | Job board (API) | No |
| [HN Who is Hiring](https://news.ycombinator.com/) | Community thread | No |
| [RemoteOK Companies](https://remoteok.com/remote-companies) | Company directory | No |
| [Himalayas Companies](https://himalayas.app/companies) | Company directory | No |
| [GitHub established-remote](https://github.com/yanirs/established-remote) | Curated list | No |
| [LinkedIn](https://www.linkedin.com/jobs/) | Job board | Cookies |
| [Indeed](https://www.indeed.com/) | Job board | No |
| [Glassdoor](https://www.glassdoor.com/Job/index.htm) | Job board | Cookies |
| [Ashby](https://www.ashbyhq.com/) (ATS) | Per-company boards | No |
| [Greenhouse](https://www.greenhouse.com/) (ATS) | Per-company boards | No |
| [Lever](https://www.lever.co/) (ATS) | Per-company boards | No |

## Installation

```bash
pip install -e .
```

## Quick Start

```bash
# Generate a config template
rjobs --init-config

# Edit config with your preferences
$EDITOR ~/.config/rjobs/config.yml

# Generate an applicant profile
rjobs --parse-resume /path/to/resume.pdf --profile my_profile

# Search all sources
rjobs --profile my_profile

# Search specific sources with extra keywords
rjobs --sources remoteok remotive himalayas --keywords "python" "backend"

# Skip LLM ranking and output JSON
rjobs --no-rank --format json

# Export to file
rjobs --export results.json
rjobs --export results.csv
```

## Applicant Profiles

Applicant profiles let the ranking step use your background and preferences instead of scoring jobs generically.

### What they do

- Parse a resume or LinkedIn profile into a structured applicant summary
- Store target roles, skills, experience areas, education, preferences, and **role keywords**
- Inject that profile into the LLM ranking prompt when you run searches with ranking enabled
- Automatically append the profile's `role_keywords` to the search keywords, so scrapers query for roles relevant to your background

If the selected profile does not exist, job ranking still runs, but without profile personalization or extra role keywords.

### Supported inputs

- PDF resumes
- Markdown resumes
- Plain-text resumes
- LinkedIn profile URLs

### Create a profile

```bash
# Create or overwrite the default profile
rjobs --parse-resume /path/to/resume.pdf

# Save to a named profile
rjobs --parse-resume /path/to/resume.md --profile backend

# Build a profile from LinkedIn instead of a local file
rjobs --parse-resume https://www.linkedin.com/in/your-name/ --profile backend
```

Profiles are saved under `~/.cache/rjobs/profiles/<name>.yml`.

### Use a profile during ranking

```bash
# Use the default profile
rjobs

# Use a named profile
rjobs --profile backend

# Search specific sources with a named profile
rjobs --profile backend --sources remoteok greenhouse lever
```

The `--profile` flag is used in two places:

- with `--parse-resume`, it controls the output profile name
- during normal searches, it selects which saved profile to inject into ranking

## Configuration

The config file lives at `~/.config/rjobs/config.yml` by default. Generate a template with:

```bash
rjobs --init-config
# or specify a custom path
rjobs --init-config /path/to/config.yml
```

### Key sections

**`credentials`** - Login details for auth-required sources. Google credentials are used for SSO on sites that support it. Browser session cookies are loaded from `~/.config/rjobs/cookies/` (see below).

**`llm`** - OpenAI-compatible API endpoint. Works with OpenAI, Ollama, vLLM, llama.cpp server, LM Studio, etc.

**`search.keywords`** - Default search terms. Extra keywords can be added via `--keywords`.

**`sources.ats_companies`** - Company slugs for Ashby, Greenhouse, and Lever ATS boards.

**`ranking`** - Threshold and system prompt for LLM ranking.

## CLI Reference

```text
rjobs [OPTIONS]
```

| Option | Description |
|---|---|
| `-h`, `--help` | Show the built-in help text and exit. |
| `--version` | Show the installed `rjobs` version and exit. |
| `--config CONFIG` | Path to `config.yml`. Defaults to `~/.config/rjobs/config.yml`. |
| `--init-config [PATH]` | Generate a template config file and exit. If `PATH` is omitted, the default config path is used. || `--init-cookies` | Create cookie template files under `~/.config/rjobs/cookies/` and exit. || `--keywords KEYWORDS [KEYWORDS ...]` | Extra search keywords appended to `search.keywords` from the config. |
| `--sources SOURCE [SOURCE ...]` | Limit the run to specific source IDs. |
| `--format {table,json,csv}` | Output format for stdout. Default: `table`. |
| `--max-results MAX_RESULTS` | Limit the number of displayed results after ranking and filtering. |
| `--max-listings MAX_LISTINGS` | Randomly sample listings to this count before ranking. Useful for debugging or limiting LLM costs. |
| `--threshold THRESHOLD` | Minimum ranking threshold from `0` to `10`. Overrides `ranking.threshold` from config. |
| `--no-rank` | Skip LLM ranking entirely. Results are still scraped, deduplicated, and output. |
| `--export FILE` | Export results to a file. `.json` and `.csv` are inferred from the extension. |
| `--parse-resume FILE_OR_URL` | Parse a resume file or LinkedIn profile URL and save an applicant profile, then exit. |
| `--profile NAME` | Profile name to save when using `--parse-resume`, or to load during ranking. Default: `default`. |
| `--show-reasoning` | Include LLM reasoning in table output. |
| `-v`, `--verbose` | Increase log verbosity. Use `-v` for INFO and `-vv` for DEBUG. |

## Authentication Notes

For sites requiring auth (Otta, Wellfound, LinkedIn, Glassdoor):

1. **Google SSO** - The tool attempts HTTP-based Google SSO login. Due to bot detection, this may not work reliably. Best used when available.

2. **Session cookies** - Export cookies from your browser and place them in individual files under `~/.config/rjobs/cookies/`. Run `rjobs --init-cookies` to create template files with instructions. Each site gets its own file (e.g. `~/.config/rjobs/cookies/linkedin`). This is the most reliable fallback, and cookies are kept separate from the main config since they expire frequently.

3. **Direct login** - Email/password login is attempted for sites that support it.

If auth fails, the scraper for that source is skipped with a warning.

## Development

```bash
pip install -e ".[dev]"
pre-commit install
```
