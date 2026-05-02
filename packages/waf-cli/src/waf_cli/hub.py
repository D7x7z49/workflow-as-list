# packages/waf-cli/src/waf_cli/hub.py

import typer

app = typer.Typer(rich_markup_mode=None, pretty_exceptions_enable=False)


@app.callback()
def main_handler(ctx: typer.Context): ...


def exec_cli():
    # set sub-commands
    # app.add_typer(xxx, name="xxx")

    app()
