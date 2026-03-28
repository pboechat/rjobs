from __future__ import annotations

import csv
import io
import json

from rich.console import Console
from rich.table import Table

from rjobs.models import JobListing


def display_table(jobs: list[JobListing], show_reasoning: bool = False) -> None:
    console = Console()

    if not jobs:
        console.print("[yellow]No job listings to display.[/yellow]")
        return

    table = Table(
        title=f"Remote Job Results ({len(jobs)} listings)",
        show_lines=True,
        expand=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Rank", style="bold cyan", width=6, justify="center")
    table.add_column("Title", style="bold", max_width=40)
    table.add_column("Company", style="green", max_width=25)
    table.add_column("Location", max_width=20)
    table.add_column("Salary", style="yellow", max_width=20)
    table.add_column("Source", style="dim", max_width=15)
    table.add_column("URL", style="blue", max_width=50, overflow="fold")

    if show_reasoning:
        table.add_column("Reasoning", style="dim italic", max_width=40)

    for idx, job in enumerate(jobs, 1):
        rank_str = f"{job.rank:.1f}" if job.rank is not None else "-"
        row = [
            str(idx),
            rank_str,
            job.title,
            job.company,
            job.location or "Remote",
            job.salary or "-",
            job.source.value,
            job.url,
        ]
        if show_reasoning:
            row.append(job.rank_reasoning or "")
        table.add_row(*row)

    console.print(table)


def _job_to_dict(job: JobListing) -> dict:
    return {
        "title": job.title,
        "company": job.company,
        "url": job.url,
        "source": job.source.value,
        "location": job.location,
        "salary": job.salary,
        "description": job.description[:500] if job.description else "",
        "tags": job.tags,
        "posted_date": job.posted_date.isoformat() if job.posted_date else None,
        "remote_type": job.remote_type,
        "rank": job.rank,
        "rank_reasoning": job.rank_reasoning,
    }


def to_json(jobs: list[JobListing]) -> str:
    return json.dumps([_job_to_dict(j) for j in jobs], indent=2, default=str)


def to_csv(jobs: list[JobListing]) -> str:
    output = io.StringIO()
    fieldnames = [
        "rank",
        "title",
        "company",
        "location",
        "salary",
        "source",
        "url",
        "description",
        "tags",
        "posted_date",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for job in jobs:
        writer.writerow(
            {
                "rank": job.rank,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "salary": job.salary,
                "source": job.source.value,
                "url": job.url,
                "description": (job.description or "")[:200],
                "tags": ";".join(job.tags),
                "posted_date": job.posted_date.isoformat() if job.posted_date else "",
            }
        )

    return output.getvalue()
