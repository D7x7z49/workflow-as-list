# packages/wal-runtime/src/wal_runtime/util.py

import re
import hashlib
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from typing import Iterator, List, Optional, Tuple
from abc import ABC, abstractmethod

from wal_core.constants import SYMBOL_DOT
from wal_core.schema import (
    ImportLine,
    LineItem,
    ReferenceNode,
    SHA256Hash,
    StepLine,
    VariableLine,
)
from wal_core.util import get_ref_placeholder, get_text_ref_hash

from wal_runtime.constants import WORKFLOW_FILE_EXTENSION
from wal_runtime.schema import Environment


# ----------------------------------------------------------------------
#  Execution interface
# ----------------------------------------------------------------------
class WorkflowExecutor(ABC):
    @abstractmethod
    def exec_shell(self, command: str, stdin: Optional[str] = None) -> Tuple[str, bool]: ...

    @abstractmethod
    def ask_question(self, question: str) -> bool: ...

    @abstractmethod
    def call_agent(self, message: str) -> str: ...


# ----------------------------------------------------------------------
#  File loading helpers
# ----------------------------------------------------------------------
def match_domain(hostname: str, patterns: List[str]) -> bool:
    if not hostname:
        return False
    for pattern in patterns:
        regex = re.escape(pattern).replace(r"\*", "[^.]*") + "$"
        if re.match(regex, hostname):
            return True
    return False


def compute_file_hash(file_path: Path) -> SHA256Hash:
    sha = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def iter_local_lines(file_path: Path) -> Iterator[str]:
    try:
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                yield line.rstrip("\n")
    except OSError as exc:
        raise RuntimeError(f"cannot read file {file_path}") from exc


def fetch_and_cache_remote(url: str, cache_dir: Path, allowed_domains: List[str]) -> Path:
    hostname = urlparse(url).hostname or ""
    if not allowed_domains:
        raise ValueError("no allowed import domains configured")
    if not match_domain(hostname, allowed_domains):
        raise ValueError(f"domain {hostname} is not in the import whitelist")

    url_hash = hashlib.sha256(url.encode()).hexdigest()
    cache_file = cache_dir / f"{url_hash}.{WORKFLOW_FILE_EXTENSION}"

    if not cache_file.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                with cache_file.open("w", encoding="utf-8") as out:
                    for line in response:
                        out.write(line.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"http error {exc.code} for {url}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"network error while fetching {url}") from exc

    return cache_file


# ----------------------------------------------------------------------
#  Replacement engine
# ----------------------------------------------------------------------
def resolve_text(
    env: Environment,
    text: str,
    *,
    executor: Optional[WorkflowExecutor] = None,
    resolving: Optional[set[SHA256Hash]] = None,
) -> str:
    if not text:
        return text

    ref_hashes = get_text_ref_hash(text)
    for ref_hash in ref_hashes:
        node = env.context.ref_map.get(ref_hash)
        if node is None:
            raise ValueError(f"Substitution reference {ref_hash} not found in module {env.context.namespace}")
        value = resolve_reference(env, node, executor=executor, resolving=resolving)
        placeholder = get_ref_placeholder(ref_hash)
        text = text.replace(placeholder, value)
    return text


def resolve_reference(
    env: Environment,
    node: ReferenceNode,
    *,
    executor: Optional[WorkflowExecutor] = None,
    resolving: Optional[set[SHA256Hash]] = None,
) -> str:
    line, target_env = lookup_label_in_env(env, node.reference)
    value = get_line_value(target_env, line, node.reference, executor=executor, resolving=resolving)

    if node.pipe:
        if executor is None:
            raise RuntimeError("Shell execution not available for pipe substitution")
        stdout, _ = executor.exec_shell(node.pipe, stdin=value)
        return stdout

    return value


def lookup_label_in_env(env: Environment, reference: str) -> Tuple[LineItem, Environment]:
    parts = reference.split(SYMBOL_DOT)
    current_env = env

    for part in parts[:-1]:
        if part not in current_env.import_map:
            raise ValueError(f"Import alias '{part}' not found in module {current_env.context.namespace}")
        current_env = current_env.import_map[part]

    final_name = parts[-1]
    module = current_env.context
    if final_name in module.label_map:
        return module.label_map[final_name], current_env
    raise ValueError(f"Label '{final_name}' not found in module {module.namespace}")


def get_line_value(
    env: Environment,
    line: LineItem,
    name_hint: str,
    *,
    executor: Optional[WorkflowExecutor] = None,
    resolving: Optional[set[SHA256Hash]] = None,
) -> str:
    if isinstance(line, VariableLine):
        raw_value = env.variable_map.get(line.name, line.text)
        if raw_value is None:
            raise ValueError(f"Variable '{name_hint}' not found in module {env.context.path}")
        return resolve_text(env, raw_value, executor=executor, resolving=resolving)
    elif isinstance(line, StepLine):
        if line.tag and line.tag in env.step_output_map:
            return env.step_output_map[line.tag]
        raise ValueError(f"Step output for '{name_hint}' not yet computed")
    elif isinstance(line, ImportLine):
        raise ValueError(f"Cannot use import alias '{name_hint}' as a value")
    raise ValueError(f"Unknown line type for '{name_hint}'")


# ----------------------------------------------------------------------
#  Cyclic import detection helpers
# ----------------------------------------------------------------------
class CircularImportError(Exception):
    def __init__(self, path: str, namespace: SHA256Hash) -> None:
        super().__init__(f"Circular import detected for module '{path}' (namespace {namespace})")
        self.path = path
        self.namespace = namespace
