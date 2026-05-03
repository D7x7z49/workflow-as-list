# packages/waf-runtime/src/waf_runtime/hub.py

from pathlib import Path
from typing import Iterator, Generator

from pydantic import AnyUrl

from waf_core.hub import parse_workflow
from waf_core.schema import (
    ImportPath,
    ImportLine,
    SHA256Hash,
    StepLine,
    StepMode,
    VariableLine,
    WorkflowModule,
)
from waf_core.util import build_block_from_step, build_root_block

from waf_runtime.config.schema import RuntimeConfig
from waf_runtime.constants import REMOTE_WORKFLOW_CACHE_ROOT
from waf_runtime.schema import Environment, Frame, StepRecord
from waf_runtime.util import (
    CircularImportError,
    compute_file_hash,
    fetch_and_cache_remote,
    iter_local_lines,
    lookup_label_in_env,
    resolve_text,
    WorkflowExecutor,
)


class WorkflowRuntime:
    def __init__(self, path: ImportPath, config: RuntimeConfig, executor: WorkflowExecutor) -> None:
        self.config: RuntimeConfig = config
        self.executor: WorkflowExecutor = executor
        self.module_cache: dict[SHA256Hash, WorkflowModule] = {}

        # Preload with cycle detection — pass an empty set for tracking
        self.root_module = self.load_module(path)
        self.root_env = self.preload_module(self.root_module, set())
        self.frames: list[Frame] = []

    # ------------------------------------------------------------------
    #  Module loading
    # ------------------------------------------------------------------
    def load_module(self, path: ImportPath) -> WorkflowModule:
        namespace = self._compute_namespace(path)
        if namespace in self.module_cache:
            return self.module_cache[namespace]

        lines = self._read_lines(path)
        module = parse_workflow(namespace, path, lines)
        self.module_cache[namespace] = module
        return module

    def _compute_namespace(self, path: ImportPath) -> SHA256Hash:
        local_path = path if isinstance(path, Path) else self._ensure_cached_remote(str(path))
        return compute_file_hash(local_path)

    def _read_lines(self, path: ImportPath) -> Iterator[str]:
        if isinstance(path, AnyUrl):
            if path.scheme in ("http", "https"):
                file_path = self._ensure_cached_remote(str(path))
                return iter_local_lines(file_path)
            elif path.scheme == "file":
                from urllib.request import url2pathname

                local_path = Path(url2pathname(str(path)))
            else:
                raise ValueError(f"unsupported scheme {path.scheme}, expected [http, https, file]")
        else:
            local_path = Path(str(path))
        return iter_local_lines(local_path)

    def _ensure_cached_remote(self, url: str) -> Path:
        allowed = self.config.white_list.domain if self.config.white_list else []
        return fetch_and_cache_remote(
            url=url,
            cache_dir=REMOTE_WORKFLOW_CACHE_ROOT,
            allowed_domains=allowed,
        )

    # ------------------------------------------------------------------
    #  Preloading (with cyclic import detection)
    # ------------------------------------------------------------------
    def preload_module(self, module: WorkflowModule, loading: set[SHA256Hash]) -> Environment:
        namespace = module.namespace
        if namespace in loading:
            raise CircularImportError(str(module.path), namespace)
        loading.add(namespace)

        env = Environment(context=module)

        for lineno in sorted(module.line_map.keys()):
            line = module.line_map[lineno]
            if isinstance(line, ImportLine):
                child_module = self.load_module(line.path)
                # Pass a copy of loading? No, we want to detect cycles across the whole tree.
                child_env = self.preload_module(child_module, loading)
                env.import_map[line.alias] = child_env
            elif isinstance(line, VariableLine):
                env.variable_map[line.name] = line.text

        loading.discard(namespace)
        return env

    # ------------------------------------------------------------------
    #  Execution
    # ------------------------------------------------------------------
    def run(self) -> None:
        for _ in self.iter_steps():
            pass

    def iter_steps(self) -> Generator[StepRecord, None, None]:
        root_block = build_root_block(self.root_module)
        if not root_block:
            return

        self.frames = [Frame(environment=self.root_env, block=root_block, pc=0)]

        while self.frames:
            frame = self.frames[-1]

            if frame.pc >= len(frame.block):
                self.frames.pop()
                continue

            step = frame.block[frame.pc]

            try:
                resolved_text = resolve_text(frame.environment, step.text, executor=self.executor)
            except Exception as e:
                raise RuntimeError(
                    f"Resolution error at step {frame.environment.context.path}:{step.lineno}: {e}"
                ) from e

            result_text = ""
            success = False

            if step.mode == StepMode.PLAIN:
                result_text = self.executor.call_agent(resolved_text)
                success = True
            elif step.mode == StepMode.SHELL:
                result_text, success = self.executor.exec_shell(resolved_text)
            elif step.mode == StepMode.QUESTION:
                success = self.executor.ask_question(resolved_text)
                result_text = str(success)

            if step.tag:
                frame.environment.step_output_map[step.tag] = result_text

            yield StepRecord(
                step=step,
                resolved_text=resolved_text,
                result_text=result_text,
                success=success,
            )

            if step.jump is not None and success:
                try:
                    target_line, target_env = lookup_label_in_env(frame.environment, step.jump)
                except ValueError as e:
                    raise ValueError(f"Jump target error at {frame.environment.context.path}:{step.lineno}: {e}") from e

                if not isinstance(target_line, StepLine):
                    raise ValueError(
                        f"Jump target '{step.jump}' resolved to non-step at "
                        f"{target_env.context.path}:{target_line.lineno}"
                    )

                # Build sub-block from the target step's module context
                sub_block = build_block_from_step(target_env.context, target_line)

                # Advance caller frame to next instruction
                frame.pc += 1

                # Push new frame with the target environment
                self.frames.append(Frame(environment=target_env, block=sub_block, pc=0))
            else:
                frame.pc += 1
