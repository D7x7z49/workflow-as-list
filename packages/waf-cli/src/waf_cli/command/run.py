# packages/waf-cli/src/waf_cli/command/run.py
import typer

from waf_core.constants import StepMode
from waf_core.schema import ImportPathAdapter
from waf_runtime.pydantic_agent.hub import PydanticAIWorkflowExecutor
from waf_runtime.hub import WorkflowRuntime

from waf_cli.schema import CommandContext


sub_run_option = typer.Typer(help="Run workflows and interactive sessions")


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

        step_count = 0
        for record in runtime.iter_steps():
            step_count += 1
            step = record.step

            mode_str = f"[{step.mode.value}]"
            if step.tag:
                header = f"$ ({step.tag}) {mode_str} {record.resolved_text}"
            else:
                header = f"$ {mode_str} {record.resolved_text}"

            typer.echo(header)

            match step.mode:
                case StepMode.PLAIN:
                    output = record.result_text
                case StepMode.SHELL:
                    output = record.result_text.strip() if record.success else f"ERROR:\n{record.result_text.strip()}"
                case StepMode.QUESTION:
                    output = "Yes" if record.success else "No"
                case _:
                    output = "unknown mode"

            typer.echo("---")
            for line in output.splitlines():
                if line.strip():
                    typer.echo(f"{line}")
            status = "[OK]" if record.success else "[NO]"
            typer.echo(f"{status}")
            typer.echo("---")

        typer.echo("\n---\n")
        typer.echo(f"Workflow {file} executed successfully with agent {agent}")
    except Exception as e:
        typer.echo("\n---\n")
        typer.echo(f"Error executing workflow: {e}", err=True)
        raise typer.Exit(1)


@sub_run_option.command()
def repl() -> None:
    typer.echo("REPL command not yet implemented")
