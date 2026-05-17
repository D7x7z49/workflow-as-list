# test/wal_runtime/execution.unit.test.py
"""Unit tests for the WorkflowRuntime execution loop (run)."""

from wal_core.constants import StepMode
from wal_core.schema import StepLine
from wal_runtime.hub import WorkflowRuntime
from wal_runtime.schema import RunFinishedEvent, RunStatus

from ..conftest import make_module


def add_step(module, lineno, text, *, depth=0, mode=StepMode.PLAIN, tag=None, jump=None):
    step = StepLine(lineno=lineno, depth=depth, mode=mode, tag=tag, jump=jump, text=text)
    module.line_map[lineno] = step
    if tag:
        module.label_map[tag] = step
    return step


def create_runtime(executor, config, root_mod, mocker, extra_mods=None):
    """Mock WorkflowRuntime.load_module and return a runtime instance."""
    modules = {str(root_mod.path): root_mod}
    if extra_mods:
        for m in extra_mods:
            modules[str(m.path)] = m
    mocker.patch.object(WorkflowRuntime, "load_module", side_effect=lambda path: modules[str(path)])
    return WorkflowRuntime(root_mod.path, config, executor)


class TestExecution:
    def test_plain_step(self, fake_executor, config, mocker):
        mod = make_module("exec")
        add_step(mod, 1, "hello")
        runtime = create_runtime(fake_executor, config, mod, mocker)
        for _ in runtime.run():
            pass
        assert fake_executor.agent_calls == ["hello"]

    def test_mode_dispatch(self, fake_executor, config, mocker):
        mod = make_module("exec_dispatch")
        add_step(mod, 1, "cmd", mode=StepMode.SHELL)
        add_step(mod, 2, "ask", mode=StepMode.QUESTION)
        runtime = create_runtime(fake_executor, config, mod, mocker)
        for _ in runtime.run():
            pass
        assert fake_executor.shell_commands == [("cmd", None)]
        assert fake_executor.questions == ["ask"]

    def test_output_stored(self, fake_executor, config, mocker):
        mod = make_module("exec_output")
        add_step(mod, 1, "compute", tag="res")
        fake_executor.agent_responses["compute"] = "42"
        runtime = create_runtime(fake_executor, config, mod, mocker)
        for _ in runtime.run():
            pass
        assert runtime.root_env.step_output_map["res"] == "42"

    def test_jump_in_module(self, fake_executor, config, mocker):
        mod = make_module("exec_jump")
        add_step(mod, 1, "step1")
        add_step(mod, 2, "jump", mode=StepMode.SHELL, jump="dest")
        add_step(mod, 3, "step3")
        # inside becomes child of step3 → part of root block
        add_step(mod, 10, "inside", depth=1, tag="dest")

        runtime = create_runtime(fake_executor, config, mod, mocker)
        for _ in runtime.run():
            pass

        # shell command executed
        assert fake_executor.shell_commands == [("jump", None)]

        # step1 before step3
        assert fake_executor.agent_calls.index("step1") < fake_executor.agent_calls.index("step3")

        # inside executed twice: once in root block (as child of step3),
        # once via the jump sub‑frame
        assert fake_executor.agent_calls.count("inside") == 2

    def test_jump_across_modules(self, fake_executor, config, mocker):
        parent = make_module("p", namespace="1" * 64)
        child = make_module("c", namespace="2" * 64)
        add_step(parent, 1, "start")
        add_step(parent, 2, "jump", mode=StepMode.SHELL, jump="sub.act")
        add_step(parent, 3, "end")
        add_step(child, 1, "child action", tag="act")

        runtime = create_runtime(fake_executor, config, parent, mocker, extra_mods=[child])
        parent_env = runtime.preload_module(parent, set())
        child_env = runtime.preload_module(child, set())
        parent_env.import_map["sub"] = child_env
        runtime.root_env = parent_env
        for _ in runtime.run():
            pass
        assert fake_executor.agent_calls == ["start", "child action", "end"]

    def test_jump_not_taken_on_false(self, fake_executor, config, mocker):
        mod = make_module("exec_false_jump")
        add_step(mod, 1, "proceed?", mode=StepMode.QUESTION, jump="skip")
        add_step(mod, 2, "fallback")
        # skip target not added – it must not be reached
        fake_executor.question_responses["proceed?"] = False
        runtime = create_runtime(fake_executor, config, mod, mocker)
        for _ in runtime.run():
            pass
        assert fake_executor.agent_calls == ["fallback"]

    def test_jump_to_invalid_label_raises(self, fake_executor, config, mocker):
        mod = make_module("exec_invalid_jump")
        add_step(mod, 1, "bad", mode=StepMode.SHELL, jump="missing")
        runtime = create_runtime(fake_executor, config, mod, mocker)
        events = list(runtime.run())
        last = events[-1]
        assert isinstance(last, RunFinishedEvent)
        assert last.status == RunStatus.FAIL
        assert last.error is not None
        assert "Label 'missing' not found" in last.error.message

    def test_empty_root_block(self, fake_executor, config, mocker):
        mod = make_module("exec_empty")
        runtime = create_runtime(fake_executor, config, mod, mocker)
        for _ in runtime.run():
            pass
        assert fake_executor.agent_calls == []
