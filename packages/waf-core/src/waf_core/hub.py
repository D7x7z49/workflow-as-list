# packages/waf-core/src/waf_core/hub.py

from typing import Iterator

from waf_core.schema import ImportPath, SHA256Hash, WorkflowModule
from waf_core.util import parse_line


def parse_workflow(
    namespace: SHA256Hash,
    path: ImportPath,
    lines: Iterator[str],
) -> WorkflowModule:
    module = WorkflowModule(path=path, namespace=namespace)
    for lineno, line in enumerate(lines, start=1):
        parse_line(module, line, lineno)

    return module
