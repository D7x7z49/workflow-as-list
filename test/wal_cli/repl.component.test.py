# test/wal_cli/repl.component.test.py


import pytest

from wal_runtime.repl import ReplRuntime
from wal_runtime.schema import RuntimeConfigProtocol, WhiteList
from wal_runtime.util import WorkflowExecutor

from wal_cli.command.repl import _save_session, _handle_meta_command


# ------------------------------------------------------------------
#  Test doubles
# ------------------------------------------------------------------


class _FakeConfig(RuntimeConfigProtocol):
    white_list: WhiteList = WhiteList(domain=[], command=[])


class _FakeExecutor(WorkflowExecutor):
    def exec_shell(self, command, stdin=None):
        return f"shell: {command}", True

    def ask_question(self, question):
        return True

    def call_agent(self, message):
        return f"agent: {message}"


class _FakeAgentMemoryConfig:
    enabled: bool = True


class _FakeAgentConfig:
    memory: _FakeAgentMemoryConfig = _FakeAgentMemoryConfig()


class _FakeAgent(_FakeExecutor):
    """A mock Agent-like object with _messages list and config."""

    def __init__(self):
        self._messages: list = []
        self.config = _FakeAgentConfig()


# ------------------------------------------------------------------
#  Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def repl():
    config = _FakeConfig()
    executor = _FakeExecutor()
    return ReplRuntime(config, executor)


@pytest.fixture
def agent():
    return _FakeAgent()


# ------------------------------------------------------------------
#  _save_session tests
# ------------------------------------------------------------------


class TestSaveSession:
    def test_save_empty_session(self, repl, tmp_path):
        path = tmp_path / "out.wal"
        result = _save_session(repl, str(path))
        assert "(no steps to save)" in result

    def test_save_single_step(self, repl, tmp_path):
        repl.execute_line("hello world")
        path = tmp_path / "out.wal"
        result = _save_session(repl, str(path))
        assert "saved 1 step" in result
        content = path.read_text()
        assert content == "- hello world\n"

    def test_save_multiple_steps(self, repl, tmp_path):
        repl.execute_line("! ls")
        repl.execute_line("? continue?")
        repl.execute_line("(x) summarize")
        path = tmp_path / "out.wal"
        result = _save_session(repl, str(path))
        assert "saved 3 step" in result
        lines = path.read_text().splitlines()
        assert lines == ["- ! ls", "- ? continue?", "- (x) summarize"]

    def test_saved_file_has_newline_end(self, repl, tmp_path):
        repl.execute_line("step")
        path = tmp_path / "out.wal"
        _save_session(repl, str(path))
        assert path.read_text().endswith("\n")


# ------------------------------------------------------------------
#  _handle_meta_command tests
# ------------------------------------------------------------------


class TestMetaCommand:
    def test_help(self, repl, agent):
        result = _handle_meta_command("/help", repl, agent)
        assert result is not None
        assert "WAL REPL" in result
        assert "/help" in result

    def test_exit(self, repl, agent):
        assert _handle_meta_command("/exit", repl, agent) == "EXIT"
        assert _handle_meta_command("/quit", repl, agent) == "EXIT"

    def test_clear(self, repl, agent):
        repl.execute_line("(x) one")
        agent._messages.append("dummy")
        result = _handle_meta_command("/clear", repl, agent)
        assert result is not None
        assert "cleared" in result
        assert len(repl.step_output_map) == 0
        assert len(agent._messages) == 0

    def test_context_empty(self, repl, agent):
        result = _handle_meta_command("/context", repl, agent)
        assert result is not None
        assert "no tagged outputs" in result

    def test_context_with_outputs(self, repl, agent):
        repl.execute_line("(a) first")
        repl.execute_line("(b) second")
        result = _handle_meta_command("/context", repl, agent)
        assert result is not None
        assert "a:" in result
        assert "b:" in result

    def test_history_empty(self, repl, agent):
        result = _handle_meta_command("/history", repl, agent)
        assert result is not None
        assert "no steps executed" in result

    def test_history_with_steps(self, repl, agent):
        repl.execute_line("step one")
        repl.execute_line("! cmd")
        result = _handle_meta_command("/history", repl, agent)
        assert result is not None
        assert "step one" in result
        assert "! cmd" in result

    def test_memory_on(self, repl, agent):
        result = _handle_meta_command("/memory on", repl, agent)
        assert result is not None
        assert "enabled" in result
        assert agent.config.memory.enabled is True

    def test_memory_off(self, repl, agent):
        result = _handle_meta_command("/memory off", repl, agent)
        assert result is not None
        assert "disabled" in result
        assert agent.config.memory.enabled is False

    def test_memory_no_arg(self, repl, agent):
        result = _handle_meta_command("/memory", repl, agent)
        assert result is not None
        assert "usage" in result

    def test_save_no_arg(self, repl, agent):
        result = _handle_meta_command("/save", repl, agent)
        assert result is not None
        assert "usage" in result

    def test_save_with_path(self, repl, agent, tmp_path):
        repl.execute_line("hello")
        path = tmp_path / "session.wal"
        result = _handle_meta_command(f"/save {path}", repl, agent)
        assert result is not None
        assert "saved" in result
        assert path.exists()
        assert path.read_text() == "- hello\n"

    def test_unknown_command(self, repl, agent):
        result = _handle_meta_command("/foo", repl, agent)
        assert result is not None
        assert "unknown command" in result
