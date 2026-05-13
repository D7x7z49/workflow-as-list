#!/usr/bin/env python3
# scripts/fix_headers.py

import fnmatch
import argparse
from functools import lru_cache
import json
from pathlib import Path
from typing import Optional


IGNORE_DIRS: set[str] = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".cache",
    ".idea",
    ".vscode",
}

# fmt: off
COMMENT_STYLES: list[tuple[str, list[str]]] = [
    ("# {rel}", [
        "py", "pyw", "pyx", "pxd", "pxi",      # Python / Cython
        "sh", "bash", "zsh", "fish", "ksh",    # Shell
        "ps1", "psm1", "psd1",                 # PowerShell
        "pl", "pm", "t",                       # Perl
        "rb", "rake", "gemspec",               # Ruby
        "php", "phtml",                        # PHP
        "yaml", "yml",                         # YAML
        "toml",                                # TOML
        "ini", "cfg", "conf", "cnf",           # Config / INI
        "env", "envrc",                        # Env files
        "hcl", "tf", "tfvars",                 # HashiCorp / Terraform
        "r", "rprofile",                       # R
        "makefile", "dockerfile",              # Special filenames as suffix
        "properties", "editorconfig", "gitignore", "gitattributes", "wal"
    ]),
    ("// {rel}", [
        "c", "h", "cpp", "cxx", "cc", "hpp", "hxx", "hh", # C / C++
        "java", "kt", "kts", "groovy", "gradle", "scala", # JVM
        "js", "mjs", "cjs", "ts", "tsx", "jsx",           # JavaScript
        "go",               # Go
        "rs",               # Rust
        "swift",            # Swift
        "cs",               # C#
        "dart",             # Dart
        "json5", "jsonc",   # JSON with comments
        "proto",            # Protobuf
    ]),
    ("-- {rel}", [
        "sql", "psql", "mysql", # SQL dialects
        "lua",                  # Lua
        "hs", "lhs",            # Haskell
        "ada", "adb", "ads",    # Ada
        "elm",                  # Elm
        "vhd", "vhdl",          # VHDL
    ]),
    ("<!-- {rel} -->", [
        "html", "htm", "xhtml", "xml", "xsl", "xslt", "svg", # HTML & XML
        "md", "markdown",   # Markdown
    ]),
    ("/* {rel} */", [
        "css", "scss", "sass", "less", "pcss", # CSS & pre‑processors
    ]),
    ("; {rel}", [
        "asm", "s", "nasm", "inc", # Assembly
    ]),
]
# fmt: on

SUFFIX_SET = set([suffix for _, suffixes in COMMENT_STYLES for suffix in suffixes])


def get_comment_line(path: Path) -> Optional[str]:
    root = get_project_root()
    rel = path.resolve().relative_to(root).as_posix()

    for comment, suffixes in COMMENT_STYLES:
        for suffix in suffixes:
            if path.suffix == f".{suffix}":
                return comment.format(rel=rel)
    return None


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    start = Path.cwd()
    while start != start.parent:
        if start.joinpath(".git").is_dir():
            break
        start = start.parent
    else:
        raise RuntimeError("could not find project root")
    return start


def load_gitignore_patterns() -> list[str]:
    patterns = []
    gitignore_path = get_project_root().joinpath(".gitignore")
    if not gitignore_path.exists():
        return patterns

    for line in gitignore_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("!"):
            patterns.append(line)
    return patterns


def should_exclude(path: Path, gitignore_patterns: list[str]) -> bool:
    try:
        rel_path = path.relative_to(get_project_root())
    except ValueError:
        rel_path = path

    rel_str = str(rel_path)

    for pattern in gitignore_patterns:
        if pattern.endswith("/"):
            if fnmatch.fnmatch(rel_str + "/", pattern) or fnmatch.fnmatch(rel_str, pattern.rstrip("/")):
                return True
        elif fnmatch.fnmatch(rel_str, pattern) or fnmatch.fnmatch(rel_str, f"**/{pattern}"):
            return True
        elif pattern.startswith("/"):
            if fnmatch.fnmatch(rel_str, pattern[1:]) or fnmatch.fnmatch(rel_str, f"**/{pattern[1:]}"):
                return True

    return False


def should_ignore_dir(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def collect_target_files(paths: list[Path]) -> set[Path]:
    target_files = set()
    gitignore_patterns = load_gitignore_patterns()

    for path in paths:
        if path.is_file():
            if (
                path.suffix.lstrip(".") in SUFFIX_SET
                and not should_ignore_dir(path)
                and not should_exclude(path, gitignore_patterns)
            ):
                target_files.add(path)

        elif path.is_dir():
            for file_path in path.rglob("*"):
                if (
                    file_path.is_file()
                    and file_path.suffix.lstrip(".") in SUFFIX_SET
                    and not should_ignore_dir(file_path)
                    and not should_exclude(file_path, gitignore_patterns)
                ):
                    target_files.add(file_path)

    return target_files


def process_file(path: Path) -> str:

    comment_line = get_comment_line(path)
    if comment_line is None:
        return "skipped"

    data = path.read_text()
    lines = data.splitlines()

    if len(lines) == 0:
        path.write_text(f"{comment_line}\n")
        return "added"

    if lines[0].strip() == comment_line:
        return "skipped"

    if not lines[0].startswith("#!"):
        lines.insert(0, comment_line)
        path.write_text("\n".join(lines) + "\n")
        return "modified"

    if len(lines) >= 2 and lines[1].strip() == comment_line:
        return "skipped"

    lines.insert(1, comment_line)
    path.write_text("\n".join(lines) + "\n")
    return "modified"


def print_info(operation: str, message: str):
    match operation:
        case "added":
            msg = f"[+] {message}"
        case "modified":
            msg = f"[~] {message}"
        case "skipped":
            msg = f"[-] {message}"
        case "error":
            msg = f"[!] {message}"
    return msg


def main():
    parser = argparse.ArgumentParser(description="check or fix file header comments")
    parser.add_argument("paths", nargs="+", help="file or directory to process")
    parser.add_argument("--quiet", action="store_true", help="suppress output")

    args = parser.parse_args()

    paths = [Path(p) for p in args.paths]
    paths = collect_target_files(paths)

    stats = {"added": 0, "modified": 0, "skipped": 0, "error": 0}

    log_list = []
    for path in paths:
        try:
            operation = process_file(path)
            msg = None
        except Exception as e:
            operation = "error"
            msg = f"{e}"
        finally:
            stats[operation] += 1
            msg = print_info(operation, f"{path}" if msg is None else f"{path}: {msg}")
            log_list.append(msg)

    if not args.quiet:
        print("\n".join(log_list))
        print(f"[*] {json.dumps(stats)}")


if __name__ == "__main__":
    main()
