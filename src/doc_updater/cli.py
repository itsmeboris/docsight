"""Command-line interface for doc-updater."""

from __future__ import annotations

import os
from pathlib import Path

import click


@click.group()
@click.option(
    "--repo",
    default=None,
    metavar="PATH",
    help="Path to the repository root (default: current directory).",
)
@click.pass_context
def cli(ctx: click.Context, repo: str | None) -> None:
    """doc-updater: detect stale documentation."""
    ctx.ensure_object(dict)
    ctx.obj["repo"] = Path(repo) if repo is not None else Path(os.getcwd())


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialise doc-updater in the repository."""
    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".doc-updater"

    # Create the store directory (idempotent).
    store_dir.mkdir(parents=True, exist_ok=True)

    # Add entry to .gitignore (idempotent — only add if not already present).
    gitignore = repo / ".gitignore"
    entry = ".doc-updater/"

    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")
        if entry not in existing:
            # Ensure we start on a fresh line.
            if existing and not existing.endswith("\n"):
                existing += "\n"
            gitignore.write_text(existing + entry + "\n", encoding="utf-8")
    else:
        gitignore.write_text(entry + "\n", encoding="utf-8")

    click.echo(f"Initialized doc-updater in {store_dir}")
