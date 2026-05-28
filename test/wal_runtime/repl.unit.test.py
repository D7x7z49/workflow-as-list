# test/wal_runtime/repl.unit.test.py

from typing import Optional, Tuple

import pytest

from wal_core.constants import StepMode
from wal_runtime.repl import ReplRuntime
from wal_runtime.schema import RuntimeConfigProtocol, WhiteList
from wal_runtime.util import WorkflowExecutor


# ------------------------------------------------------------------
#  Minimal test doubles
# ------------------------------------------------------------------


class _FakeConfig(RuntimeConfigProtocol):
    white_list: WhiteList = WhiteList(domain=[], command=[])


class _FakeExecutor(WorkflowExecutor):
    """Returns canned responses keyed by command / message text."""

    def __init__(
        self,
        *,
        shell_outputs: Optional[dict[str, Tuple[str, bool]]] = None,
        agent_outputs: Optional[dict[str, str]] = None,
        question_outputs: Optional[dict[str, bool]] = None,
    ) -> None:
        self._shell = shell_outputs or {}
        self._agent = agent_outputs or {}
        self._question = question_outputs or {}

    def exec_shell(self, command: str, stdin: Optional[str] = None) -> Tuple[str, bool]:
        if command in self._shell:
            return self._shell[command]
        return "", True

    def ask_question(self, question: str) -> bool:
        if question in self._question:
            return self._question[question]
        return False

    def call_agent(self, message: str) -> str:
        if message in self._agent:
            return self._agent[message]
        return "ok"


@pytest.fixture
def repl():
    config = _FakeConfig()
    executor = _FakeExecutor(
        agent_outputs={"hello": "world", "one": "ONE", "two": "TWO", "A": "alpha", "B": "beta"},
        shell_outputs={"ls": ("file.txt\n", True)},
        question_outputs={"approve?": True},
    )
    return ReplRuntime(config, executor)


# ------------------------------------------------------------------
#  Tests
# ------------------------------------------------------------------


class TestStepModeDetection:
    def test_shell_step(self, repl):
        record = repl.execute_line("! ls")
        assert record.step.mode == StepMode.SHELL
        assert record.step.text == "ls"
        assert record.success is True
        assert record.result_text == "file.txt\n"
        assert record.resolved_text == "ls"

    def test_question_step(self, repl):
        record = repl.execute_line("? approve?")
        assert record.step.mode == StepMode.QUESTION
        assert record.step.text == "approve?"
        assert record.success is True
        assert record.result_text == "True"

    def test_plain_step(self, repl):
        record = repl.execute_line("hello")
        assert record.step.mode == StepMode.PLAIN
        assert record.step.text == "hello"
        assert record.success is True
        assert record.result_text == "world"


class TestTagAssignment:
    def test_tag_stored_in_output_map(self, repl):
        repl.execute_line("(greeting) hello")
        assert "greeting" in repl.step_output_map
        assert repl.step_output_map["greeting"] == "world"

    def test_tag_on_step_line(self, repl):
        record = repl.execute_line("(x) hello")
        assert record.step.tag == "x"

    def test_duplicate_tag_raises(self, repl):
        repl.execute_line("(dup) hello")
        with pytest.raises(ValueError, match="Duplicate step tag"):
            repl.execute_line("(dup) hello")

    def test_tag_persists_across_steps(self, repl):
        repl.execute_line("(a) one")
        repl.execute_line("(b) two")
        assert repl.step_output_map == {"a": "ONE", "b": "TWO"}


class TestSubstitution:
    def test_tag_reference_resolved(self, repl):
        repl.execute_line("(x) hello")
        record = repl.execute_line("use ${x}")
        assert record.resolved_text == "use world"

    def test_unknown_tag_left_as_is(self, repl):
        record = repl.execute_line("use ${unknown}")
        assert record.resolved_text == "use ${unknown}"

    def test_multiple_substitutions(self, repl):
        repl.execute_line("(a) A")
        repl.execute_line("(b) B")
        record = repl.execute_line("${a} and ${b}")
        assert record.resolved_text == "alpha and beta"


class TestHistory:
    def test_history_records_original_text(self, repl):
        repl.execute_line("! ls")
        assert len(repl.history) == 1
        raw, record = repl.history[0]
        assert raw == "! ls"
        assert record.step.text == "ls"  # parsed text (without "!" prefix)

    def test_history_accumulates(self, repl):
        repl.execute_line("one")
        repl.execute_line("two")
        assert len(repl.history) == 2


class TestClear:
    def test_clear_resets_everything(self, repl):
        repl.execute_line("(x) one")
        repl.clear()
        assert len(repl.step_output_map) == 0
        assert len(repl.history) == 0
        # Tag should be reusable after clear.
        repl.execute_line("(x) two")
        assert repl.step_output_map["x"] == "TWO"


class TestInvalidInput:
    def test_invalid_input_raises(self, repl):
        with pytest.raises(ValueError, match="REPL input must be a step"):
            repl.execute_line("> (alias) ./file.wal")

        with pytest.raises(ValueError, match="REPL input must be a step"):
            repl.execute_line(": name = value")

        with pytest.raises(ValueError, match="REPL input must be a step"):
            repl.execute_line("# comment")
