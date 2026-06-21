from __future__ import annotations

import json
from pathlib import Path

import typer

from app.schemas.prompt import PromptGenerateRequest
from app.services.json_validator import JsonValidator
from app.services.prompt_generator import PromptGenerator

cli = typer.Typer(help="CLI cho AI Video Rewriter & Video Rebuilder")


@cli.command()
def generate_prompt(
    youtube_url: str,
    rewrite_style: str,
    target_audience: str,
    tone: str,
    target_duration: str,
    retention_mode: str,
    hook_style: str,
    clip_strategy: str,
    reuse_level: str,
    content_density: str,
):
    payload = PromptGenerateRequest(
        youtube_url=youtube_url,
        rewrite_style=rewrite_style,
        target_audience=target_audience,
        tone=tone,
        target_duration=target_duration,
        retention_mode=retention_mode,
        hook_style=hook_style,
        clip_strategy=clip_strategy,
        reuse_level=reuse_level,
        content_density=content_density,
    )
    typer.echo(PromptGenerator().generate(payload))


@cli.command()
def validate_json(file_path: Path):
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    valid, errors, _ = JsonValidator().validate(payload)
    if valid:
        typer.echo("JSON hợp lệ.")
    else:
        for err in errors:
            typer.echo(err)
        raise typer.Exit(1)


if __name__ == "__main__":
    cli()
