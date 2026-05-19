# packages/wal-runtime/src/wal_runtime/hub.py

from pathlib import Path
from typing import Iterator, Generator

from pydantic import AnyUrl

from wal_core.constants import StepMode
from wal_core.schema import (
    ImportPath,
    ImportLine,
    SHA256Hash,
    StepLine,
    VariableLine,
    WorkflowModule,
)
from wal_core.hub import parse_workflow
from wal_core.util import build_block_from_step, build_root_block

from wal_runtime.schema import (
    Environment,
    ErrorInfo,
    Frame,
    RunEvent,
    RuntimeConfigProtocol,
    StepCompletedEvent,
    StepRecord,
    RunFinishedEvent,
    RunStatus,
)
from wal_runtime.util import (
    CircularImportError,
    compute_file_hash,
    fetch_and_cache_remote,
    iter_local_lines,
    lookup_label_in_env,
    resolve_text,
    WorkflowExecutor,
)


class WorkflowRuntime:
    def __init__(self, home: Path, path: ImportPath, config: RuntimeConfigProtocol, executor: WorkflowExecutor) -> None:
        self.home: Path = home
        self.config: RuntimeConfigProtocol = config
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

    @property
    def _cache_path(self):
        return self.home / "cache"

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
        remote_cache_dir = self._cache_path / "remote"
        allowed = self.config.white_list.domain if self.config.white_list else []
        return fetch_and_cache_remote(
            url=url,
            cache_dir=remote_cache_dir,
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
    def run(self) -> Generator[RunEvent, None, None]:
        try:
            for data in self.iter_steps():
                yield StepCompletedEvent(record=data)
            yield RunFinishedEvent(status=RunStatus.DONE)
        except Exception as e:
            error_info = ErrorInfo.from_exception(e)
            yield RunFinishedEvent(status=RunStatus.FAIL, error=error_info)

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
                pc=frame.pc,
                module_path=frame.environment.context.path,
                module_hash=frame.environment.context.namespace,
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
            elif step.jump is None and not success:
                raise RuntimeError(f"Step failed at {step.lineno} line in {step.text}")
            else:
                frame.pc += 1
