# test/wal_runtime/preload.unit.test.py
"""Unit tests for module preloading (Environment tree construction)."""

import pytest

from wal_runtime.hub import WorkflowRuntime
from wal_runtime.util import CircularImportError

from ..conftest import make_module


class TestPreloadModule:
    def test_variables_kept_unchanged(self, fake_executor, config, mocker, workspace):
        mod = make_module("preload_vars")
        from wal_core.util import parse_line

        parse_line(mod, ": msg = hello ${world}", 1)

        mocker.patch.object(WorkflowRuntime, "load_module", return_value=mod)
        runtime = WorkflowRuntime(
            home=workspace,
            path=mod.path,
            config=config,
            executor=fake_executor,
        )
        env = runtime.preload_module(mod, set())
        assert "__SUBST_" in env.variable_map["msg"]
        assert "${world}" not in env.variable_map["msg"]

    def test_import_env_hierarchy(self, fake_executor, config, mocker, workspace):
        child = make_module("preload_child")
        from wal_core.util import parse_line

        parse_line(child, ": val = 1", 1)

        parent = make_module("preload_parent")
        parse_line(parent, "> (c)http://example.com/preload_child", 1)

        modules = {
            str(parent.path): parent,
            str(child.path): child,
        }

        mocker.patch.object(WorkflowRuntime, "load_module", side_effect=lambda path: modules[str(path)])
        runtime = WorkflowRuntime(
            home=workspace,
            path=parent.path,
            config=config,
            executor=fake_executor,
        )

        env = runtime.preload_module(parent, set())
        assert "c" in env.import_map
        child_env = env.import_map["c"]
        assert child_env.variable_map["val"] == "1"

    def test_circular_import(self, fake_executor, config, mocker, workspace):
        a = make_module("circ_a", namespace="1" * 64)
        b = make_module("circ_b", namespace="2" * 64)
        from wal_core.util import parse_line

        parse_line(a, "> (b)http://example.com/circ_b", 1)
        parse_line(b, "> (a)http://example.com/circ_a", 1)

        # A clean root module without imports to start the runtime
        root = make_module("root", namespace="3" * 64)
        parse_line(root, ": dummy = 1", 1)

        modules = {
            str(root.path): root,
            str(a.path): a,
            str(b.path): b,
        }

        mocker.patch.object(WorkflowRuntime, "load_module", side_effect=lambda path: modules[str(path)])
        runtime = WorkflowRuntime(
            home=workspace,
            path=root.path,
            config=config,
            executor=fake_executor,
        )

        loading = {a.namespace}
        with pytest.raises(CircularImportError, match="Circular import"):
            runtime.preload_module(b, loading)

    def test_self_import(self, fake_executor, config, mocker, workspace):
        mod = make_module("self_import", namespace="s" * 64)
        from wal_core.util import parse_line

        parse_line(mod, "> (self)http://example.com/self_import", 1)

        # Clean root module
        root = make_module("root", namespace="4" * 64)
        parse_line(root, ": dummy = 1", 1)

        modules = {
            str(root.path): root,
            str(mod.path): mod,
        }

        mocker.patch.object(WorkflowRuntime, "load_module", side_effect=lambda path: modules[str(path)])
        runtime = WorkflowRuntime(
            home=workspace,
            path=root.path,
            config=config,
            executor=fake_executor,
        )

        with pytest.raises(CircularImportError, match="Circular import"):
            runtime.preload_module(mod, set())
