# packages/wal-cli/src/wal_cli/command/run.py

import hashlib
from uuid import uuid4

import typer

from wal_core.schema import ImportPathAdapter
from wal_runtime.schema import EventType, RunFinishedEvent, RunStatus, StepCompletedEvent
from wal_runtime.hub import WorkflowRuntime
from wal_cli.constants import RUNS_MAP_FILE, RUNS_ROOT
from wal_runtime.pydantic_agent.hub import PydanticAIWorkflowExecutor

from wal_cli.schema import CLI_RunMeta, CommandContext


sub_run_option = typer.Typer(help="Run workflows and interactive sessions")


def _run_event_loop(ctx: CommandContext, runtime: WorkflowRuntime, agent: str):
    run_id = hashlib.sha256(uuid4().bytes).hexdigest()
    run_meta = CLI_RunMeta(
        agent=agent,
        run_id=run_id,
        module_path=runtime.root_env.context.path,
        module_hash=runtime.root_env.context.namespace,
    )

    run_file = RUNS_ROOT / f"{run_id}.jsonl"
    run_file.touch(exist_ok=True)
    typer.echo(f"[+] {run_meta.run_id} [{run_meta.status}] <{run_file.absolute()}>")

    for event in runtime.run():
        event_type = event.event_type
        if event_type == EventType.STEP_COMPLETED and isinstance(event, StepCompletedEvent):
            run_file.open("a", encoding="utf-8").write(f"{event.record.model_dump_json()}\n")

        elif event_type == EventType.RUN_FINISHED and isinstance(event, RunFinishedEvent):
            run_meta.status = event.status

            RUNS_MAP_FILE.open("a", encoding="utf-8").write(f"{run_meta.model_dump_json()}\n")

    if run_meta.status not in [RunStatus.DONE, RunStatus.FAIL]:
        typer.echo("Run failed", err=True)
        raise typer.Exit(1)

    typer.echo(f"[=] {run_meta.run_id} [{run_meta.status}]")


@sub_run_option.command("workflow")
def exec_workflow(
    cxt: typer.Context,
    file: str,
    agent: str = typer.Option(..., "--agent", help="agent identity"),
) -> None:
    ctx: CommandContext = cxt.obj
    try:
        path = ImportPathAdapter.validate_python(file)
        executor = PydanticAIWorkflowExecutor(agent)
        runtime = WorkflowRuntime(path, ctx.config, executor)

        _run_event_loop(ctx, runtime, agent)

    except Exception as e:
        typer.echo(f"Error executing workflow: {e}", err=True)
        raise typer.Exit(1)


@sub_run_option.command()
def repl() -> None:
    typer.echo("REPL command not yet implemented")
