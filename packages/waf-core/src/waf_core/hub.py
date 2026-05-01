# packages/waf-core/src/waf_core/hub.py

from typing import Iterator, Optional, Protocol

from pydantic import NonNegativeInt
from waf_core.constants import SYMBOL_DOT
from waf_core.schema import (
    ImportLine,
    ImportPath,
    LineItem,
    Reference,
    SHA256Hash,
    WorkflowContent,
)
from waf_core.util import parse_line


class WorkflowImportStore(Protocol):
    """runtime should be able to store and retrieve workflows"""

    def set(self, key: SHA256Hash, value: WorkflowContent): ...

    def get(self, key: SHA256Hash) -> Optional[WorkflowContent]: ...


class WorkflowCallback(Protocol):
    """runtime should be able to load workflows"""

    def get_namespace(self, path: ImportPath) -> SHA256Hash: ...

    def load_workflow(self, path: ImportPath, line: Optional[NonNegativeInt] = None) -> Iterator[str]: ...


class WorkflowHub:
    def __init__(self, path: ImportPath, store: WorkflowImportStore, callback: WorkflowCallback):
        self.store: WorkflowImportStore = store
        self.callback: WorkflowCallback = callback

        namespace = self.load_import(path)
        self.root: SHA256Hash = namespace
        self.imports: dict[ImportPath, SHA256Hash] = {path: self.root}

    def get_context(self, namespace: SHA256Hash) -> WorkflowContent:
        content = self.store.get(namespace)
        if content is None:
            raise ValueError("Namespace not found")
        return content

    def load_import(self, path: ImportPath):
        iterator = self.callback.load_workflow(path)
        namespace = self.callback.get_namespace(path)
        if path not in self.imports:
            self.imports[path] = namespace

        content = self.store.get(namespace)
        if content is None:
            iterator = self.callback.load_workflow(path)
            content = WorkflowContent(path=path, namespace=namespace)
            for lineno, line in enumerate(iterator, start=1):
                parse_line(content, line, lineno)
            self.store.set(namespace, content)

        return namespace

    def load_reference(
        self, reference: Reference, context: WorkflowContent, line_info: str
    ) -> tuple[WorkflowContent, LineItem]:
        current_context = context
        current_reference = reference
        current_line_info = line_info
        visited_namespaces = set()

        while True:
            current_namespace = current_context.namespace
            if current_namespace in visited_namespaces:
                raise ValueError(
                    f"At line {current_line_info}, circular import detected for namespace '{current_namespace}'"
                )
            visited_namespaces.add(current_namespace)

            # Base case: no dot, resolve in current context
            if SYMBOL_DOT not in current_reference:
                if current_reference not in current_context.label_map:
                    raise ValueError(
                        f"At line {current_line_info}, reference '{current_reference}' not found in current context"
                    )
                return current_context, current_context.label_map[current_reference]

            # Split first part and remainder
            first_part, remainder = current_reference.split(SYMBOL_DOT, 1)

            if first_part not in current_context.label_map:
                raise ValueError(
                    f"At line {current_line_info}, import alias '{first_part}' not found in current context"
                )

            import_line = current_context.label_map[first_part]
            current_line_info = f"{current_line_info}:{import_line.lineno}"

            if not isinstance(import_line, ImportLine):
                raise ValueError(f"At line {current_line_info}, import alias '{first_part}' is not an import")

            namespace = self.imports[import_line.path]
            current_context = self.get_context(namespace)
            current_reference = remainder
