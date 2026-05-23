# packages/wal-cli/src/wal_cli/command/config.py

import json

import typer
from pydantic import ValidationError

from wal_cli.config.schema import RuntimeConfig
from wal_cli.config.util import format_model_structure
from wal_cli.config.constants import CONFIG_FILE, CONFIG_SCHEMA_FILE

from wal_cli.schema import CommandContext


sub_config_option = typer.Typer(help="manage wal configuration")


@sub_config_option.command("get")
def get_config(
    cxt: typer.Context,
    key: str = typer.Argument(..., help="config key"),
):
    context: CommandContext = cxt.obj

    # Convert to dict for JSON path navigation
    config_dict = context.config.model_dump()

    # Simple JSON path implementation (dot notation)
    keys = key.split(".")
    value = config_dict

    try:
        for k in keys:
            value = value[k]
        typer.echo(json.dumps(value, indent=2))
    except (KeyError, TypeError):
        typer.echo(f"key '{key}' not found", err=True)
        raise typer.Exit(1)


@sub_config_option.command("set")
def set_config(
    cxt: typer.Context,
    key: str = typer.Argument(..., help="config key"),
    value: str = typer.Argument(..., help="config value, json format"),
):
    context: CommandContext = cxt.obj

    # Parse the JSON value
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        typer.echo("value must be valid JSON", err=True)
        raise typer.Exit(1)

    # Get current config as dict
    config_dict = context.config.model_dump()

    # Navigate to the parent of the target key
    keys = key.split(".")
    target = config_dict

    try:
        for k in keys[:-1]:
            target = target[k]

        # Set the value
        target[keys[-1]] = parsed_value

        # Re-validate and create new config
        new_config = RuntimeConfig.model_validate(config_dict)

        data = new_config.model_dump()
        data["$schema"] = str(CONFIG_SCHEMA_FILE)

        # Write to file
        CONFIG_FILE.write_text(json.dumps(data, indent=2))

        typer.echo(f"set {key} = {parsed_value}")

    except (KeyError, TypeError) as e:
        typer.echo(f"key '{key}' not found: {e}", err=True)
        raise typer.Exit(1)
    except ValidationError as e:
        typer.echo(f"validation error: {e}", err=True)
        raise typer.Exit(1)


@sub_config_option.command("schema")
def get_config_schema(
    cxt: typer.Context,
):
    context: CommandContext = cxt.obj
    typer.echo(format_model_structure(context.config))
    typer.echo("---")
    typer.echo(f"see: <{CONFIG_SCHEMA_FILE}>")
