# packages/wal-cli/src/wal_cli/command/agent.py

import uuid

import typer

from wal_cli.agent.schema import AgentSpec
from wal_cli.config.constants import AGENT_ROOT, AGENT_SPEC_SCHEMA_FILE, SCHEMA_ROOT

sub_agent_option = typer.Typer(help="manage wal agents")


@sub_agent_option.callback()
def agent_handler(ctx: typer.Context):
    AGENT_ROOT.mkdir(parents=True, exist_ok=True)
    SCHEMA_ROOT.mkdir(parents=True, exist_ok=True)


@sub_agent_option.command("list")
def list_agents():
    agent_files = sorted(AGENT_ROOT.glob("*.agent.json"))
    if not agent_files:
        typer.echo("no agents found")
        return

    for agent_file in agent_files:
        spec = AgentSpec.from_json_file(agent_file)
        typer.echo(f"- {spec.name} at <{agent_file}>")


@sub_agent_option.command("init")
def init_agent(
    name: str = typer.Argument(..., help="agent name"),
    model: str = typer.Option(..., "--model", "-m", help="model id, `provider:model` format"),
):
    for spec_file in AGENT_ROOT.glob("*.agent.json"):
        spec = AgentSpec.from_json_file(spec_file)
        if spec.name == name:
            typer.echo(f"agent '{name}' already exists at <{spec_file}>", err=True)
            raise typer.Exit(1)

    spec = AgentSpec(id=uuid.uuid4(), name=name, model=model)
    spec_file = spec.to_json_file(AGENT_ROOT, AGENT_SPEC_SCHEMA_FILE)
    typer.echo(f"agent '{name}' initialized at <{spec_file}>")
