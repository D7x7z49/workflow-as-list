#!/usr/bin/env python3
# scripts/fix_headers.py

"""
fix_headers.py - Add/update file headers with relative path comments.

UNIX-style (#) headers, supports shebang detection, respects .gitignore.
"""

import os
import sys
import fnmatch
from pathlib import Path
from argparse import ArgumentParser
from typing import List, Set, Optional, Tuple

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

# Extensions to process (lowercase)
SUPPORTED_EXTS: Set[str] = {
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".ps1",
    ".pl",
    ".rb",
    ".php",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
    ".json5",
    ".hcl",
    ".tf",
    ".sql",
    ".lua",
    ".dockerfile",
    ".makefile",
}

# Special filenames without extension (lowercase)
SPECIAL_NAMES: Set[str] = {"makefile", "dockerfile"}

# Directories always ignored (lowercase)
IGNORE_DIRS: Set[str] = {
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

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------


def get_project_root(start: Path) -> Path:
    """
    Find project root by looking for common markers (.git, pyproject.toml, etc.)
    Falls back to parent of script's directory if script is under scripts/.
    """
    # If we're in a scripts/ directory, assume parent is root
    if start.name == "scripts" and start.parent != start:
        return start.parent
    # Otherwise walk up until we find markers
    for parent in [start] + list(start.parents):
        if (parent / ".git").exists():
            return parent
        if (parent / "pyproject.toml").exists():
            return parent
    return start  # fallback


def load_gitignore(root: Path) -> List[str]:
    """Parse .gitignore lines, return list of patterns."""
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return []
    patterns = []
    with open(gitignore, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Remove trailing slash for directories (fnmatch works with slash)
            if line.endswith("/"):
                line = line[:-1]
            patterns.append(line)
    return patterns


def should_ignore(path: Path, root: Path, ignore_patterns: List[str]) -> bool:
    """
    Check if path should be ignored based on:
      - Built-in IGNORE_DIRS (any component matches)
      - .gitignore patterns (relative to root)
      - Extra patterns from command line
    """
    # Convert to relative string with forward slashes
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        # path not under root? then ignore? better to treat as not ignored
        return False

    # Check built-in dirs: any path component in IGNORE_DIRS
    parts = rel.split("/")
    for part in parts:
        if part.lower() in IGNORE_DIRS:
            return True

    # Check patterns
    for pat in ignore_patterns:
        # fnmatch matches whole path segments; we also need to handle directory patterns
        # e.g., "build/" matches "build/file" if we already stripped trailing slash
        if fnmatch.fnmatch(rel, pat):
            return True
        # Also check if pat is a directory prefix (e.g., "build" matches "build/file")
        if pat.endswith("/"):
            pat = pat[:-1]
        if fnmatch.fnmatch(rel, pat + "/*"):
            return True
    return False


def collect_files(paths: List[str], root: Path, ignore_patterns: List[str]) -> List[Path]:
    """Collect all files from given paths (files or directories) that are supported."""
    files = []
    for p in paths:
        path = Path(p).resolve()
        if not path.exists():
            print(f"[!] Path not found: {p}")
            continue
        if path.is_file():
            if is_supported(path):
                files.append(path)
        elif path.is_dir():
            for root_dir, dirs, filenames in os.walk(path):
                # Skip ignored directories in-place
                dirs[:] = [d for d in dirs if not should_ignore(Path(root_dir) / d, root, ignore_patterns)]
                for f in filenames:
                    full = Path(root_dir) / f
                    if is_supported(full) and not should_ignore(full, root, ignore_patterns):
                        files.append(full)
    return files


def is_supported(path: Path) -> bool:
    """Check if file extension or name is supported."""
    name = path.name.lower()
    if name in SPECIAL_NAMES:
        return True
    return path.suffix.lower() in SUPPORTED_EXTS


def read_file_lines(path: Path) -> Optional[List[str]]:
    """Read file as UTF-8, return list of lines (with newlines stripped)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().splitlines()
    except Exception as e:
        print(f"[!] Error reading {path}: {e}")
        return None


def write_file_lines(path: Path, lines: List[str]) -> bool:
    """Write lines back to file with original newline style (default \n)."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            # Ensure trailing newline if original had one? Not necessary.
        return True
    except Exception as e:
        print(f"[!] Error writing {path}: {e}")
        return False


def process_file(file: Path, root: Path, dry_run: bool, quiet: bool) -> Tuple[str, str]:
    """
    Process a single file:
      - Compute relative path
      - Determine insertion line (0 or 1 based on shebang)
      - Check existing header
      - Modify if needed
    Returns (status, message) where status is "modified", "skipped", or "error".
    """
    rel = file.relative_to(root).as_posix()
    expected = f"# {rel}"

    lines = read_file_lines(file)
    if lines is None:
        return "error", f"Could not read {file}"

    # Determine insertion index
    idx = 0
    if lines and lines[0].startswith("#!"):
        idx = 1

    # Check if header is already correct
    if idx < len(lines) and lines[idx].strip() == expected:
        if not quiet:
            print(f"[*] {rel}")
        return "skipped", "Already correct"

    # Check if the target line is an existing header (starts with "# " and contains "/")
    target_line = lines[idx] if idx < len(lines) else ""
    if target_line.strip().startswith("# "):
        # Replace it
        if not dry_run:
            lines[idx] = expected
            if not write_file_lines(file, lines):
                return "error", "Write failed"
        print(f"[-] {rel}")
        return "modified", "Replaced header"
    else:
        # Insert header
        if not dry_run:
            lines.insert(idx, expected)
            if not write_file_lines(file, lines):
                return "error", "Write failed"
        print(f"[-] {rel}")
        return "modified", "Added header"


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main():
    parser = ArgumentParser(
        description="Add/update file headers with relative path comments.",
        epilog="If no paths given, processes current directory recursively.",
    )
    parser.add_argument("paths", nargs="*", help="Files or directories to process")
    parser.add_argument("--root", help="Project root directory (auto-detected if not given)")
    parser.add_argument("--ignore", action="append", default=[], help="Additional ignore patterns")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be done")
    parser.add_argument("--quiet", action="store_true", help="Suppress [*] output (skipped files)")

    args = parser.parse_args()

    # Determine project root
    if args.root:
        root = Path(args.root).resolve()
    else:
        # Try to detect from current directory
        root = get_project_root(Path.cwd())

    # Collect ignore patterns
    ignore_patterns = load_gitignore(root)
    ignore_patterns.extend(args.ignore)

    # Collect files
    if not args.paths:
        # Process current directory recursively
        paths_to_process = [str(Path.cwd())]
    else:
        paths_to_process = args.paths

    files = collect_files(paths_to_process, root, ignore_patterns)

    if not files:
        print("[!] No files to process.")
        sys.exit(0)

    # Process each file
    stats = {"modified": 0, "skipped": 0, "error": 0}
    for file in files:
        status, msg = process_file(file, root, args.dry_run, args.quiet)
        stats[status] += 1

    # Summary (only if not quiet or if any errors)
    if not args.quiet or stats["error"] > 0:
        print(f"[*] Modified: {stats['modified']}, Skipped: {stats['skipped']}, Errors: {stats['error']}")

    sys.exit(1 if stats["error"] > 0 else 0)


if __name__ == "__main__":
    main()
