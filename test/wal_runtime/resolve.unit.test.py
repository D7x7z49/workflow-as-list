# test/wal_runtime/resolve.unit.test.py
"""Unit tests for the text substitution engine."""

from typing import Optional

import pytest

from wal_core.schema import (
    ImportLine,
    ImportPathAdapter,
    ReferenceNode,
    StepMode,
    StepLine,
    VariableLine,
)
from wal_core.util import get_ref_placeholder
from wal_runtime.schema import Environment
from wal_runtime.util import (
    get_line_value,
    lookup_label_in_env,
    resolve_text,
    resolve_reference,
)

from ..conftest import make_module


@pytest.fixture
def env():
    """Empty environment, extended in tests."""
    module = make_module("resolve_test")
    return Environment(context=module)


@pytest.fixture
def env_with_data(env):
    """Environment with a variable and a step output."""
    var_line = VariableLine(name="greeting", text="hello", lineno=1)
    env.context.label_map["greeting"] = var_line
    env.variable_map["greeting"] = "hello"

    step_line = StepLine(lineno=2, depth=0, mode=StepMode.PLAIN, tag="result", text="compute")
    env.context.label_map["result"] = step_line
    env.step_output_map["result"] = "42"
    return env


def _bind_ref(env: Environment, reference: str, pipe: Optional[str] = None):
    node = ReferenceNode(reference=reference, pipe=pipe)
    ref_hash = node.fingerprint()
    env.context.ref_map[ref_hash] = node
    return get_ref_placeholder(ref_hash)


class TestLookupLabel:
    def test_simple(self, env):
        var = VariableLine(name="x", text="y", lineno=1)
        env.context.label_map["x"] = var
        line, returned_env = lookup_label_in_env(env, "x")
        assert line is var
        assert returned_env is env

    def test_dotted_import(self, env):
        child = Environment(context=make_module("c"))
        var = VariableLine(name="v", text="val", lineno=1)
        child.context.label_map["v"] = var
        env.import_map["sub"] = child
        line, ret_env = lookup_label_in_env(env, "sub.v")
        assert line is var
        assert ret_env is child

    def test_missing_alias_raises(self, env):
        child = Environment(context=make_module("c"))
        env.import_map["sub"] = child
        with pytest.raises(ValueError, match="Import alias 'bad' not found"):
            lookup_label_in_env(env, "bad.v")


def test_get_line_value_variable(env_with_data):
    line = env_with_data.context.label_map["greeting"]
    assert get_line_value(env_with_data, line, "greeting") == "hello"


def test_get_line_value_step_output(env_with_data):
    line = env_with_data.context.label_map["result"]
    assert get_line_value(env_with_data, line, "result") == "42"


def test_get_line_value_step_not_executed(env):
    step = StepLine(lineno=2, depth=0, mode=StepMode.PLAIN, tag="s", text="x")
    env.context.label_map["s"] = step
    with pytest.raises(ValueError, match="Step output for 's' not yet computed"):
        get_line_value(env, step, "s")


def test_get_line_value_import_raises(env):
    imp = ImportLine(alias="mod", path=ImportPathAdapter.validate_python("http://example.com/dummy"), lineno=1)
    with pytest.raises(ValueError, match="Cannot use import alias"):
        get_line_value(env, imp, "mod")


def test_resolve_text_empty(env):
    assert resolve_text(env, "") == ""


def test_resolve_variable(env_with_data):
    placeholder = _bind_ref(env_with_data, "greeting")
    result = resolve_text(env_with_data, f"<{placeholder}>")
    assert result == "<hello>"


def test_resolve_step_output(env_with_data):
    placeholder = _bind_ref(env_with_data, "result")
    result = resolve_text(env_with_data, f"<{placeholder}>")
    assert result == "<42>"


def test_resolve_pipe(fake_executor, env):
    var = VariableLine(name="data", text="input", lineno=1)
    env.context.label_map["data"] = var
    env.variable_map["data"] = "input"
    placeholder = _bind_ref(env, "data", pipe="upper")
    fake_executor.shell_responses["upper"] = ("INPUT", True)
    result = resolve_text(env, f"<{placeholder}>", executor=fake_executor)
    assert result == "<INPUT>"


def test_pipe_without_executor_raises(env):
    var = VariableLine(name="data", text="input", lineno=1)
    env.context.label_map["data"] = var
    env.variable_map["data"] = "input"
    placeholder = _bind_ref(env, "data", pipe="upper")
    with pytest.raises(RuntimeError, match="Shell execution not available"):
        resolve_text(env, f"<{placeholder}>")


def test_unknown_ref_hash_raises(env):
    unknown_ref_hash = "a" * 64
    placeholder = get_ref_placeholder(unknown_ref_hash)
    with pytest.raises(ValueError, match="Substitution reference"):
        resolve_text(env, placeholder)


def test_resolve_reference_directly(env_with_data):
    node = ReferenceNode(reference="greeting", pipe=None)
    assert resolve_reference(env_with_data, node) == "hello"
