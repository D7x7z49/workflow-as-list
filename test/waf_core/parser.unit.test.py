# test/waf_core/parser.unit.test.py
"""Unit tests for waf-core parser. Validates line parsing, label/ref maps, and errors."""

import pytest

from waf_core.constants import StepMode
from waf_core.schema import (
    CommentLine,
    EmptyLine,
    ImportLine,
    ImportPathAdapter,
    StepLine,
    VariableLine,
    WorkflowModule,
)
from waf_core.util import parse_line


@pytest.fixture
def module() -> WorkflowModule:
    return WorkflowModule(
        path=ImportPathAdapter.validate_python("file:///test.waf"),
        namespace="0" * 64,
    )


# ------------------------------------------------------------------
# Basic line types
# ------------------------------------------------------------------
@pytest.mark.parametrize(
    "line,expected_type",
    [
        ("", EmptyLine),
        ("   ", EmptyLine),
        ("# comment", CommentLine),
        ("  # indented", CommentLine),
        ("> (alias)file:///path", ImportLine),
        (": name = value", VariableLine),
        ("- plain", StepLine),
        ("- !shell", StepLine),
        ("- ?question", StepLine),
        ("- (tag) step", StepLine),
        ("- @targ!cmd", StepLine),
        ("  - nested", StepLine),
    ],
)
def test_line_type(module, line, expected_type):
    result = parse_line(module, line, 1)
    assert isinstance(result, expected_type)


def test_import_alias_and_path(module):
    result = parse_line(module, "> (lib)file:///lib.waf", 1)
    assert isinstance(result, ImportLine)
    assert result.alias == "lib"


def test_variable_name_and_text(module):
    result = parse_line(module, ": x = hello", 1)
    assert isinstance(result, VariableLine)
    assert result.name == "x"
    assert result.text == "hello"


def test_step_attributes(module):
    result = parse_line(module, "- (step1)@target!cmd", 1)
    assert isinstance(result, StepLine)
    assert result.tag == "step1"
    assert result.jump == "target"
    assert result.mode == StepMode.SHELL
    assert result.text == "cmd"


def test_nested_depth(module):
    result = parse_line(module, "    - deep", 1)
    assert result.depth == 2


# ------------------------------------------------------------------
# Substitutions
# ------------------------------------------------------------------
def test_substitution_creates_ref_node(module):
    result = parse_line(module, ": x = hello ${var}", 1)
    assert isinstance(result, VariableLine) or isinstance(result, StepLine)
    assert "__SUBST_" in result.text
    assert len(module.ref_map) == 1


def test_substitution_with_pipe(module):
    parse_line(module, ": x = ${var!tr}", 2)
    pipes = [v for v in module.ref_map.values() if v.pipe == "tr"]
    assert len(pipes) == 1


def test_substitution_missing_closing_brace(module):
    with pytest.raises(ValueError, match="substitution missing closing"):
        parse_line(module, ": x = ${ref", 1)


# ------------------------------------------------------------------
# Error conditions
# ------------------------------------------------------------------
@pytest.mark.parametrize(
    "line,error_msg",
    [
        ("unknown line", "prefix not found"),
        ("  > (a)file:///path", "Import lines must be at top level"),
        ("> (a/path", "import line must end with '\\)'"),
        ("  : x = a", "Variable lines must be at top level"),
        (": x a", "variable line must contain '='"),
        ("- (unclosed", "step tag missing closing '\\)'"),
        ("- @", "invalid jump reference"),
        ("- @ref", "jump reference must end with '!' or '\\?'"),
    ],
)
def test_parse_errors(module, line, error_msg):
    with pytest.raises(ValueError, match=error_msg):
        parse_line(module, line, 1)


# ------------------------------------------------------------------
# Label map
# ------------------------------------------------------------------
def test_label_map_entries(module):
    parse_line(module, "> (mod)file:///mod", 1)
    parse_line(module, "- (step1) do", 2)
    parse_line(module, ": var = x", 3)
    assert "mod" in module.label_map
    assert "step1" in module.label_map
    assert "var" in module.label_map
    assert isinstance(module.label_map["mod"], ImportLine)
    assert isinstance(module.label_map["step1"], StepLine)


def test_duplicate_tag_raises(module):
    parse_line(module, "- (tag) first", 1)
    with pytest.raises(ValueError, match="Duplicate step tag"):
        parse_line(module, "- (tag) second", 2)


def test_duplicate_import_alias_raises(module):
    parse_line(module, "> (alias)file:///a", 1)
    with pytest.raises(ValueError, match="Duplicate import alias"):
        parse_line(module, "> (alias)file:///b", 2)
