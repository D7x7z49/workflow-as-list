# packages/waf-cli/src/waf_cli/command/agent.py

import typer
from pydantic_ai import AgentSpec

from waf_cli.schema import CommandContext
from waf_runtime.pydantic_agent.constants import AGENT_ROOT
from waf_runtime.pydantic_agent.hub import init_agent_spec_file

sub_agent_option = typer.Typer(help="manage waf agents")


@sub_agent_option.command("list")
def list_agents():
    if not AGENT_ROOT.exists():
        typer.echo("No agents directory found")
        return

    agent_files = list(AGENT_ROOT.glob("*.spec.json"))
    if not agent_files:
        typer.echo("No agents found")
        return

    typer.echo("Available agents:")
    for agent_file in sorted(agent_files):
        identity = agent_file.stem
        agent_spec = AgentSpec.from_file(agent_file)
        typer.echo(f"- {identity} ({agent_spec.model}) <{str(agent_file)}>")


@sub_agent_option.command("init")
def init_agent(
    cxt: typer.Context,
    identity: str = typer.Argument(..., help="agent identity, spec file name"),
    model: str = typer.Option(..., "--model", "-m", help="model id, set `provider:model` format"),
):
    context: CommandContext = cxt.obj
    is_valid, data = context.config.validate_model_id(model)
    if not is_valid:
        typer.echo(data, err=True)
        raise typer.Exit(1)

    init_agent_spec_file(identity, model)
