# packages/wal-cli/src/wal_cli/command/repl.py

from pathlib import Path

import typer

from wal_runtime.repl import ReplRuntime
from wal_runtime.schema import StepRecord

from wal_cli.agent.hub import Agent
from wal_cli.agent.schema import AgentSpec
from wal_cli.config.constants import AGENT_ROOT

from wal_cli.schema import CommandContext


sub_repl_option = typer.Typer(help="start an interactive WAL REPL session")


_SEP = "=" * 60

_HELP_TEXT = """\
/{sep}
WAL REPL — interactive workflow execution

  type a WAL step and press Enter to execute it immediately.
  step input (no "- " prefix needed):
    text              plain LLM step
    ! command         shell step
    ? question        question step (yes/no)
    (tag) text        tagged step (output stored for ${{tag}})

  meta-commands (prefixed with /):
    /help             show this help
    /exit, /quit      exit the REPL (Ctrl-D also works)
    /clear            reset step context and agent memory
    /context          show accumulated step outputs
    /history          list executed steps
    /save <file>      save session as a .wal file
    /memory on|off    toggle agent conversation memory
{sep}""".format(sep=_SEP)


def _display_step_result(record: StepRecord, /) -> None:
    status = "ok" if record.success else "no"
    tag_info = f" [{record.step.tag}]" if record.step.tag else ""
    result = record.result_text[:200]
    if not result:
        result = "(empty response)"
    typer.echo(f"[{status}]{tag_info} {result}")


def _save_session(repl_runtime: ReplRuntime, filepath: str) -> str:
    if not repl_runtime.history:
        return "(no steps to save)"

    path = Path(filepath)
    lines: list[str] = []
    for raw_text, _record in repl_runtime.history:
        lines.append(f"- {raw_text}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"saved {len(lines)} step(s) to {path.resolve()}"


def _handle_meta_command(
    line: str,
    repl_runtime: ReplRuntime,
    executor: Agent,
) -> str | None:
    parts = line.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    match cmd:
        case "/help":
            return _HELP_TEXT
        case "/exit" | "/quit":
            return "EXIT"
        case "/clear":
            repl_runtime.clear()
            executor._messages.clear()
            return "context and agent memory cleared"
        case "/context":
            if not repl_runtime.step_output_map:
                return "(no tagged outputs)"
            lines = [f"  {tag}: {val[:80]}" for tag, val in repl_runtime.step_output_map.items()]
            return "tagged outputs:\n" + "\n".join(lines)
        case "/history":
            if not repl_runtime.history:
                return "(no steps executed)"
            lines = []
            for raw, record in repl_runtime.history:
                status = "ok" if record.success else "no"
                lines.append(f"  [{status}] {raw[:80]}")
            return "step history:\n" + "\n".join(lines)
        case "/save":
            if not arg:
                return "usage: /save <file>"
            return _save_session(repl_runtime, arg)
        case "/memory":
            if arg in ("on", "off"):
                executor.config.memory.enabled = arg == "on"
                return f"agent memory {'enabled' if arg == 'on' else 'disabled'}"
            return "usage: /memory on|off"
        case _:
            return f"unknown command: {cmd} (type /help for available commands)"


@sub_repl_option.callback(invoke_without_command=True)
def repl_command(
    cxt: typer.Context,
    agent: str = typer.Option(..., "--agent", help="agent name"),
) -> None:
    """Start an interactive WAL REPL session."""
    ctx: CommandContext = cxt.obj
    spec = AgentSpec.from_json_file_by_name(agent, AGENT_ROOT)
    if spec is None:
        typer.echo(f"agent '{agent}' not found at <{AGENT_ROOT}>", err=True)
        raise typer.Exit(1)

    executor = Agent(spec, ctx.config.agent_config)
    repl_runtime = ReplRuntime(ctx.config, executor)

    typer.echo(_HELP_TEXT)

    step_count = 0
    try:
        while True:
            try:
                line = input(f"wal[{agent}]:{step_count}> ")
            except EOFError:
                typer.echo()
                break
            except KeyboardInterrupt:
                typer.echo()
                continue

            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("/"):
                result = _handle_meta_command(stripped, repl_runtime, executor)
                if result == "EXIT":
                    break
                if result:
                    typer.echo(result)
                continue

            try:
                step_count += 1
                record = repl_runtime.execute_line(stripped)
                _display_step_result(record)
            except Exception as e:
                typer.echo(f"[!] {e}", err=True)
    finally:
        typer.echo(f"bye ({step_count} steps)")
