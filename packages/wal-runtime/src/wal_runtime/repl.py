# packages/wal-runtime/src/wal_runtime/repl.py

from typing import cast

from pydantic import AnyUrl

from wal_core.constants import StepMode
from wal_core.schema import ImportPath, StepLine, WorkflowModule
from wal_core.util import SUBSTITUTION_RE as _SUBST_RE, parse_line

from wal_runtime.schema import RuntimeConfigProtocol, StepRecord
from wal_runtime.util import WorkflowExecutor

# Synthetic import path for REPL sessions.
# A file:// URL passes AnyUrl validation without requiring a real file
# on disk, unlike wal_core.schema.FilePath.
_REPL_PATH: ImportPath = cast(ImportPath, AnyUrl("file:///<repl>"))


class ReplRuntime:
    """Interactive single-step execution engine for WAL REPL.

    Unlike WorkflowRuntime (which loads a complete .wal file and
    runs it top-to-bottom), ReplRuntime accepts one step at a time,
    executes it immediately, and accumulates state across steps.

    Public interface:
      - execute_line(text) -> StepRecord — parse and execute one step.
      - clear() — reset all accumulated state.
    """

    def __init__(self, config: RuntimeConfigProtocol, executor: WorkflowExecutor) -> None:
        self.config: RuntimeConfigProtocol = config
        self.executor: WorkflowExecutor = executor

        # Per‑step output, keyed by step tag (identifier).
        self.step_output_map: dict[str, str] = {}

        # Ordered history: (original_raw_text, StepRecord).
        self.history: list[tuple[str, StepRecord]] = []

        # Internal synthetic module used as parsing context.
        # parse_line() appends lines here so label_map and line_map
        # grow across calls — duplicate tags are naturally rejected.
        self._context = WorkflowModule(
            path=_REPL_PATH,
            namespace="0" * 64,
        )
        self._lineno = 0

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------
    def execute_line(self, text: str) -> StepRecord:
        """Parse *text* as a WAL step line and execute it.

        The caller may omit the leading -  prefix; it is automatically
        prepended.  ${tag} references are resolved from previous step
        outputs before execution.

        Returns a StepRecord describing the completed step.
        """
        self._lineno += 1
        lineno = self._lineno

        raw_text = text

        # 1. Validate: REPL only supports step lines.
        if text.startswith(("#", ">", ":")):
            raise ValueError(
                f"REPL input must be a step (text, ! shell, ? question, or (tag) text), "
                f"got line starting with '{text[0]}'"
            )

        # 2. Parse as a valid WAL step line (prefix "- " added).
        wal_line = f"- {text}"
        line_item = parse_line(self._context, wal_line, lineno)

        if not isinstance(line_item, StepLine):
            raise ValueError(
                f"Expected a WAL step, got {type(line_item).__name__}. "
                f"REPL input must be a step (text, ! shell, ? question, or (tag) text)."
            )

        step_line = line_item

        # 3. Post‑resolve ${tag} placeholders left by parse_substitution.
        resolved_text = self._post_resolve(step_line.text)

        # 4. Execute via the executor.
        result_text: str
        success: bool

        if step_line.mode == StepMode.SHELL:
            result_text, success = self.executor.exec_shell(resolved_text)
        elif step_line.mode == StepMode.QUESTION:
            success = self.executor.ask_question(resolved_text)
            result_text = str(success)
        else:  # StepMode.PLAIN
            result_text = self.executor.call_agent(resolved_text)
            success = True

        # 5. Store tagged output.
        if step_line.tag:
            self.step_output_map[step_line.tag] = result_text

        # 6. Build record.
        record = StepRecord(
            step=step_line,
            pc=lineno - 1,
            module_path=_REPL_PATH,
            module_hash="0" * 64,
            resolved_text=resolved_text,
            result_text=result_text,
            success=success,
        )

        self.history.append((raw_text, record))
        return record

    def clear(self) -> None:
        """Reset all accumulated state.

        Clears step outputs, history, and the internal parsing context.
        Agent memory (executor.call_agent message history) is *not*
        reset — that is the caller's responsibility.
        """
        self.step_output_map.clear()
        self.history.clear()
        self._lineno = 0
        self._context = WorkflowModule(
            path=_REPL_PATH,
            namespace="0" * 64,
        )

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------
    def _post_resolve(self, text: str) -> str:
        """Replace __SUBST_<hash>__ placeholders with actual values.

        After parse_line runs parse_substitution, ${tag}
        references in the step text have been replaced by __SUBST_
        placeholders and stored in context.ref_map.  This method
        walks the parsed text and resolves each placeholder:

        - Known tags → value from step_output_map.
        - Unknown tags → literal ${ref} (reconstructed).
        """

        def _replace(match):
            ref_hash = match.group(1)
            node = self._context.ref_map.get(ref_hash)
            if node is None:
                return match.group(0)
            if node.reference in self.step_output_map:
                return self.step_output_map[node.reference]
            return f"${{{node.reference}}}"

        return _SUBST_RE.sub(_replace, text)
