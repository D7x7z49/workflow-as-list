# packages/wal-cli/src/wal_cli/command/run.py

import bisect
import hashlib
from uuid import uuid4

import typer
from pydantic import NonNegativeInt

from wal_core.schema import ImportPathAdapter
from wal_runtime.schema import (
    EventType,
    RunFinishedEvent,
    RunStatus,
    StepCompletedEvent,
    StepRecord,
)
from wal_runtime.hub import WorkflowRuntime
from wal_cli.constants import ID_PREFIX_LENGTH, RUNS_MAP_FILE, RUNS_ROOT
from wal_runtime.pydantic_agent.hub import PydanticAIWorkflowExecutor

from wal_cli.schema import CLI_RunMeta, CommandContext


sub_run_option = typer.Typer(help="Run workflows and interactive sessions")


def _run_event_loop(ctx: CommandContext, runtime: WorkflowRuntime, agent: str) -> CLI_RunMeta:
    run_id = hashlib.sha256(uuid4().bytes).hexdigest()
    run_meta = CLI_RunMeta(
        agent=agent,
        run_id=run_id,
        module_path=runtime.root_env.context.path,
        module_hash=runtime.root_env.context.namespace,
    )

    run_file = RUNS_ROOT / f"{run_id}.jsonl"
    run_file.parent.mkdir(parents=True, exist_ok=True)
    run_file.touch(exist_ok=True)

    for event in runtime.run():
        event_type = event.event_type
        if event_type == EventType.STEP_COMPLETED and isinstance(event, StepCompletedEvent):
            with run_file.open("a", encoding="utf-8") as f:
                f.write(f"{event.record.model_dump_json()}\n")
                f.flush()

        elif event_type == EventType.RUN_FINISHED and isinstance(event, RunFinishedEvent):
            run_meta.status = event.status
            with RUNS_MAP_FILE.open("a", encoding="utf-8") as f:
                f.write(f"{run_meta.model_dump_json()}\n")
                f.flush()

    if run_meta.status not in [RunStatus.DONE, RunStatus.FAIL]:
        typer.echo("Run failed", err=True)
        raise typer.Exit(1)

    return run_meta


@sub_run_option.command("workflow")
def exec_workflow(
    cxt: typer.Context,
    file: str,
    agent: str = typer.Option(..., "--agent", help="agent identity"),
    format: str = typer.Option("text", "--format", help="Output format: text, json, id"),
) -> None:
    ctx: CommandContext = cxt.obj
    try:
        path = ImportPathAdapter.validate_python(file)
        executor = PydanticAIWorkflowExecutor(agent)
        runtime = WorkflowRuntime(path, ctx.config, executor)

        run_meta = _run_event_loop(ctx, runtime, agent)

        run_id = run_meta.run_id
        run_file = RUNS_ROOT / f"{run_id}.jsonl"

        if format == "json":
            typer.echo(run_meta.model_dump_json())
        elif format == "id":
            typer.echo(run_id)
        else:
            typer.echo(f"[#S] {run_id[:ID_PREFIX_LENGTH]} [{run_meta.status.value}] <{run_file.absolute()}>")
            typer.echo(f"[#E] {run_id[:ID_PREFIX_LENGTH]} [{run_meta.status.value}]")

    except Exception as e:
        typer.echo(f"Error executing workflow: {e}", err=True)
        raise typer.Exit(1)


@sub_run_option.command("list")
def list_runs(
    limit: int = typer.Option(20, "--limit", help="Number of runs to show"),
    reverse: bool = typer.Option(False, "--reverse", help="Reverse order"),
) -> None:
    if not RUNS_MAP_FILE.exists():
        typer.echo("No runs found")
        return

    runs: list[CLI_RunMeta] = []
    with RUNS_MAP_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = CLI_RunMeta.model_validate_json(line)
            bisect.insort(runs, data, key=lambda r: r.created_at)
            if len(runs) > limit:
                runs.pop(0) if reverse else runs.pop()

    if len(runs) == 0:
        typer.echo("No run data found")
        return

    for run in runs:
        typer.echo(
            f"- {run.run_id[:ID_PREFIX_LENGTH]} [{run.status.value}] <{run.module_path}:{run.module_hash[:ID_PREFIX_LENGTH]}>"
        )


@sub_run_option.command("show")
def show_run(
    id: str = typer.Argument(..., help="Run ID (full hash or 8-char prefix)"),
    index: NonNegativeInt = typer.Option(1, "--index", help="Step index"),
    limit: NonNegativeInt = typer.Option(1, "--limit", help="Number of steps to show"),
) -> None:
    if not RUNS_MAP_FILE.exists():
        typer.echo("No runs found")
        return

    run_meta: CLI_RunMeta | None = None
    with RUNS_MAP_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = CLI_RunMeta.model_validate_json(line)
            if data.run_id == id or data.run_id[:ID_PREFIX_LENGTH] == id:
                run_meta = data

    if run_meta is None:
        typer.echo(f"[{id}] file not found")
        return

    run_path = RUNS_ROOT / f"{run_meta.run_id}.jsonl"

    steps: list[StepRecord] = []
    with run_path.open("r", encoding="utf-8") as f:
        for step, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            if step < index:
                continue
            steps.append(StepRecord.model_validate_json(line))
            if len(steps) == limit:
                break

    if len(steps) == 0:
        typer.echo(f"[{id}] step not found")
        return

    typer.echo(f"[#S] [{id}] step {index}-{index + len(steps)} ({len(steps)} total)")
    for record in steps:
        typer.echo("=" * 12)
        typer.echo(
            f"[+] [{'ok' if record.success else 'no'}] [{record.pc}] [{record.module_hash[:ID_PREFIX_LENGTH]}:{record.module_path}:{record.step.lineno}]"
        )
        typer.echo("-" * 12)
        typer.echo(record.resolved_text)
        typer.echo("-" * 12)
        typer.echo(record.result_text)
    else:
        typer.echo("=" * 12)
    typer.echo(f"[#E] [{id}] end ({len(steps)} steps)")


@sub_run_option.command()
def repl() -> None:
    typer.echo("REPL command not yet implemented")
