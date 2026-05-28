# packages/wal-cli/src/wal_cli/hub.py
import typer

from wal_cli.config.constants import RUNS_MAP_FILE
from wal_cli.config.hub import load_config
from wal_cli.command.config import sub_config_option
from wal_cli.command.agent import sub_agent_option
from wal_cli.command.run import sub_run_option
from wal_cli.command.repl import sub_repl_option

from wal_cli.schema import CommandContext

app = typer.Typer(rich_markup_mode=None, pretty_exceptions_enable=False)

# Register sub-commands
app.add_typer(sub_config_option, name="config")
app.add_typer(sub_agent_option, name="agent")
app.add_typer(sub_repl_option, name="repl")
app.add_typer(sub_run_option, name="run")


@app.callback()
def main_handler(ctx: typer.Context):
    config = load_config()
    ctx.obj = CommandContext(config=config)

    # Ensure RUNS_MAP_FILE exists
    RUNS_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    RUNS_MAP_FILE.touch(exist_ok=True)


def exec_cli():
    app()
