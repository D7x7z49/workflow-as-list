# test/wal_core/block.unit.test.py
"""Unit tests for block building helpers: build_block_from_step and build_root_block."""

from wal_core.constants import StepMode
from wal_core.schema import StepLine, CommentLine, WorkflowModule, ImportPathAdapter
from wal_core.util import build_block_from_step, build_root_block


def fake_module() -> WorkflowModule:
    return WorkflowModule(
        path=ImportPathAdapter.validate_python("http://example.com/x"),
        namespace="0" * 64,
    )


def make_step(lineno: int, depth: int, tag=None) -> StepLine:
    return StepLine(lineno=lineno, depth=depth, mode=StepMode.PLAIN, tag=tag, text="step")


# ------------------------------------------------------------------
# build_block_from_step
# ------------------------------------------------------------------
def test_single_step():
    m = fake_module()
    s = make_step(1, 0)
    m.line_map[1] = s
    block = build_block_from_step(m, s)
    assert block == [s]


def test_includes_child():
    m = fake_module()
    p = make_step(1, 0)
    c = make_step(2, 1)
    m.line_map[1] = p
    m.line_map[2] = c
    block = build_block_from_step(m, p)
    assert block == [p, c]


def test_stops_at_same_depth():
    m = fake_module()
    a = make_step(1, 0)
    b = make_step(2, 1)
    c = make_step(3, 0)
    m.line_map[1] = a
    m.line_map[2] = b
    m.line_map[3] = c
    block = build_block_from_step(m, a)
    assert block == [a, b]


def test_stops_at_shallower_depth():
    m = fake_module()
    parent = make_step(2, 1)
    child = make_step(3, 2)
    uncle = make_step(4, 1)
    m.line_map[2] = parent
    m.line_map[3] = child
    m.line_map[4] = uncle
    block = build_block_from_step(m, parent)
    assert block == [parent, child]


def test_skips_non_step_lines():
    m = fake_module()
    s = make_step(1, 0)
    m.line_map[1] = s
    m.line_map[2] = CommentLine(lineno=2, depth=1, text="comment")
    block = build_block_from_step(m, s)
    assert block == [s]


# ------------------------------------------------------------------
# build_root_block
# ------------------------------------------------------------------
def test_empty_module_returns_empty():
    m = fake_module()
    assert build_root_block(m) == []


def test_single_root_step():
    m = fake_module()
    s = make_step(1, 0)
    m.line_map[1] = s
    assert build_root_block(m) == [s]


def test_multiple_roots():
    m = fake_module()
    a = make_step(1, 0)
    b = make_step(2, 0)
    m.line_map[1] = a
    m.line_map[2] = b
    assert build_root_block(m) == [a, b]


def test_flattens_nested():
    m = fake_module()
    root = make_step(1, 0)
    child = make_step(2, 1)
    root2 = make_step(3, 0)
    m.line_map[1] = root
    m.line_map[2] = child
    m.line_map[3] = root2
    assert build_root_block(m) == [root, child, root2]


def test_ignores_deep_only_steps():
    m = fake_module()
    s = make_step(1, 1)
    m.line_map[1] = s
    assert build_root_block(m) == []
