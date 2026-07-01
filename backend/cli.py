"""
RAG Debugger CLI — rag-debug command entry point.
Usage: rag-debug run --config pipeline.yaml --queries queries.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(
    name="rag-debug",
    help="RAG Quality Debugger — automated diagnostic tool for RAG pipeline failure attribution.",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError:
        err_console.print("[red]pyyaml not installed. Run: pip install pyyaml[/red]")
        raise typer.Exit(1)

    from backend.security.pickle_detector import PickleDetectedError, check_bytes
    try:
        check_bytes(path.read_bytes(), source=str(path))
    except PickleDetectedError as e:
        err_console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    with open(path) as f:
        return yaml.safe_load(f)


def _load_json(path: Path) -> list:
    from backend.security.pickle_detector import PickleDetectedError, check_bytes
    try:
        check_bytes(path.read_bytes(), source=str(path))
    except PickleDetectedError as e:
        err_console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("queries", [])


@app.command("run")
def run_diagnosis(
    config: Path = typer.Option(..., "--config", "-c", help="Pipeline config YAML file"),
    queries: Path = typer.Option(..., "--queries", "-q", help="Failing queries JSON file"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output report file (.md or .json)"),
    redact_pii: bool = typer.Option(False, "--redact-pii", help="Redact PII before external API calls"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
) -> None:
    """Run full diagnostic pipeline and print report."""

    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    console.print(Panel.fit(
        "[bold cyan]RAG Quality Debugger[/bold cyan] v1.0\n"
        "Automated failure attribution for RAG pipelines",
        border_style="cyan",
    ))

    # Load and validate config
    if not config.exists():
        err_console.print(f"[red]Config file not found: {config}[/red]")
        raise typer.Exit(1)
    if not queries.exists():
        err_console.print(f"[red]Queries file not found: {queries}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Loading config:[/dim] {config}")
    raw_config = _load_yaml(config)

    console.print(f"[dim]Loading queries:[/dim] {queries}")
    raw_queries = _load_json(queries)

    # Validate
    try:
        from backend.models.config import PipelineConfig, QueryBatch
        pipeline_config = PipelineConfig(**raw_config)
        query_batch = QueryBatch(queries=raw_queries)
    except Exception as e:
        err_console.print(f"[red]Validation error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"\n[green]✓[/green] Config valid: [bold]{pipeline_config.name}[/bold]")
    console.print(f"[green]✓[/green] Queries: {len(query_batch.queries)} | Mode: {'supervised' if query_batch.is_supervised else 'unsupervised'}")
    console.print()

    # Run diagnosis
    asyncio.run(_run_async(pipeline_config, query_batch, output, redact_pii))


async def _run_async(pipeline_config, query_batch, output, redact_pii):
    from backend.db.database import AsyncSessionFactory, init_db
    from backend.services.session_service import SessionService
    from backend.services.report_service import ReportService

    await init_db()

    async with AsyncSessionFactory() as db:
        service = SessionService(db)
        report_service = ReportService(db)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Building BM25 oracle index...", total=None)

            session_orm = await service.create_session(
                pipeline_config=pipeline_config,
                query_batch=query_batch,
                redact_pii=redact_pii,
            )

            progress.update(task, description=f"Running diagnosis ({len(query_batch.queries)} queries)...")

            await service.run_diagnosis(
                session_id=session_orm.id,
                pipeline_config=pipeline_config,
                query_batch=query_batch,
                redact_pii=redact_pii,
            )

            progress.update(task, description="Building report...")
            session_full = await service.get_session_full(session_orm.id)

        report = await report_service.build_report(session_full)

    # Print summary table
    _print_summary(report)

    # Output file
    if output:
        if str(output).endswith(".json"):
            output.write_text(report.model_dump_json(indent=2))
            console.print(f"\n[green]✓[/green] JSON report written to: {output}")
        else:
            md = report_service.render_markdown(report)
            output.write_text(md)
            console.print(f"\n[green]✓[/green] Markdown report written to: {output}")
    else:
        md = report_service.render_markdown(report)
        console.print("\n" + md)


def _print_summary(report) -> None:
    s = report.summary

    table = Table(title="Diagnosis Summary", show_header=True, header_style="bold cyan")
    table.add_column("Query", style="dim", max_width=50)
    table.add_column("Diagnosis", min_width=25)
    table.add_column("Confidence", justify="center")
    table.add_column("Retrieval", justify="center")
    table.add_column("Generation", justify="center")

    _COLORS = {
        "retrieval_failure": "yellow",
        "generation_failure": "magenta",
        "compound_failure": "red",
        "data_quality_failure": "red",
        "no_failure_detected": "green",
        "insufficient_evidence": "dim",
    }

    for qd in report.query_diagnoses:
        color = _COLORS.get(qd.final_diagnosis, "white")
        table.add_row(
            qd.query_text[:48] + ("…" if len(qd.query_text) > 48 else ""),
            f"[{color}]{qd.final_diagnosis}[/{color}]",
            f"{qd.confidence_score:.0%}",
            qd.retrieval_verdict,
            qd.generation_verdict,
        )

    console.print(table)

    if report.recommendations:
        console.print(f"\n[bold]Top Recommendation:[/bold]")
        top = report.recommendations[0]
        console.print(Panel(
            f"[bold]{top.title}[/bold]\n\n{top.description[:300]}",
            border_style="yellow",
            subtitle=f"Effort: {top.effort} | Impact: {top.impact}",
        ))


@app.command("validate")
def validate_config(
    config: Path = typer.Option(..., "--config", "-c", help="Pipeline config YAML file"),
) -> None:
    """Validate a pipeline config file without running diagnosis."""
    raw = _load_yaml(config)
    try:
        from backend.models.config import PipelineConfig
        cfg = PipelineConfig(**raw)
        console.print(f"[green]✓ Valid config:[/green] {cfg.name}")
        console.print(f"  Fingerprint: {cfg.fingerprint()}")
        console.print(f"  Vector DB:   {cfg.vector_db.provider} / {cfg.vector_db.collection_name}")
        console.print(f"  Embedding:   {cfg.embedding.provider} / {cfg.embedding.model_id}")
        console.print(f"  LLM:         {cfg.llm.provider} / {cfg.llm.model_id}")
        console.print(f"  top_k:       {cfg.retrieval.top_k}")
        if not cfg.prompt:
            console.print("[yellow]  ⚠ No prompt config — generation diagnostics will be skipped[/yellow]")
    except Exception as e:
        err_console.print(f"[red]✗ Invalid config:[/red] {e}")
        raise typer.Exit(1)


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind"),
    port: int = typer.Option(8765, help="Port to bind"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code change"),
) -> None:
    """Start the local API server (for UI integration)."""
    try:
        import uvicorn
    except ImportError:
        err_console.print("[red]uvicorn not installed. Run: pip install uvicorn[standard][/red]")
        raise typer.Exit(1)

    console.print(Panel.fit(
        f"[bold cyan]RAG Debugger API[/bold cyan]\n"
        f"Serving at http://{host}:{port}\n"
        f"Docs:      http://{host}:{port}/docs",
        border_style="cyan",
    ))
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    app()
