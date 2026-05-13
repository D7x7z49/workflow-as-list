# packages/wal-core/src/wal_core/hub.py

from typing import Iterator

from wal_core.schema import ImportPath, SHA256Hash, WorkflowModule
from wal_core.util import parse_line


def parse_workflow(
    namespace: SHA256Hash,
    path: ImportPath,
    lines: Iterator[str],
) -> WorkflowModule:
    module = WorkflowModule(path=path, namespace=namespace)
    for lineno, line in enumerate(lines, start=1):
        parse_line(module, line, lineno)

    return module
