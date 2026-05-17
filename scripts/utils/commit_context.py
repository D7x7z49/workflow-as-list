# scripts/utils/commit_context.py
# Generate formatted context for LLM to write a Conventional Commits message.
# Usage: python commit_context.py [--src-key dir1 ...] [--test-key dir1 ...] [--exclude-key pattern ...]

import argparse
import subprocess
from pathlib import Path

ROOT = Path.cwd()
SPEC_PATH = ROOT / "prompt/git/commit/conventional-commits.md"

# Full set of Conventional Commits community types
ALL_TYPES = {"feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert"}

# Types excluded when no source code paths are present
EXCLUDE_SRC_TYPES = {"feat", "fix", "refactor", "perf", "style"}

# Type excluded when no test paths are present
EXCLUDE_TEST_TYPE = {"test"}

# get diff file list
LIST_DIFF = "git --no-pager diff --staged --name-only"
CONTENT_DIFF = "git --no-pager diff --staged"


def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        exit(result.returncode)
    return result.stdout


def build_exclude_args(exclude_patterns):
    """Build git pathspec exclude arguments from patterns like '*.lock'."""
    args = []
    for pattern in exclude_patterns:
        args.append(f":!{pattern}")
    return args


def get_changed_files():
    """Return list of changed file paths from staged diff (no exclusions)."""
    output = run(LIST_DIFF)
    return [line.strip() for line in output.split("\n") if line.strip()]


def path_has_component(path, components):
    """Check if any path segment matches a component name."""
    parts = path.replace("\\", "/").rstrip("/").split("/")
    for part in parts:
        if part in components:
            return True
    for comp in components:
        if path.startswith(comp + "/"):
            return True
    return False


def determine_allowed(files, src_key, test_key):
    """Return set of allowed commit types based on changed file paths."""
    has_src = any(path_has_component(f, src_key) for f in files)
    has_test = any(path_has_component(f, test_key) for f in files)

    excluded = set()
    if not has_src:
        excluded |= EXCLUDE_SRC_TYPES
    if not has_test:
        excluded |= EXCLUDE_TEST_TYPE

    return ALL_TYPES - excluded


def main():
    parser = argparse.ArgumentParser(description="Generate commit context for LLM.")

    SRC_KEY_HELP = "Source directory names (default: ['src'])."
    parser.add_argument("--src-key", nargs="*", default=["src"], help=SRC_KEY_HELP)

    TEST_KEY_HELP = "Test directory names (default: ['test', 'tests'])."
    parser.add_argument("--test-key", nargs="*", default=["test", "tests"], help=TEST_KEY_HELP)

    EXCLUDE_KEY_HELP = "Glob patterns to exclude from diff (default: ['*.lock'])."
    parser.add_argument("--exclude-key", nargs="*", default=["*.lock"], help=EXCLUDE_KEY_HELP)

    args = parser.parse_args()

    src_key = args.src_key
    test_key = args.test_key
    exclude_key = args.exclude_key

    # Build exclude args for git diff
    exclude_args = build_exclude_args(exclude_key)
    exclude_str = " ".join(exclude_args)

    # Get staged diff content (with exclusions)
    content_command = f"{CONTENT_DIFF} -- {exclude_str}"
    diff = run(content_command)
    if len(diff.encode()) < 4:
        exit(1)

    # Get changed file paths (no exclusions, for type analysis and display)
    files = get_changed_files()

    # Determine allowed types
    allowed = determine_allowed(files, src_key, test_key)
    has_src = any(path_has_component(f, src_key) for f in files)
    has_test = any(path_has_component(f, test_key) for f in files)

    # Get spec
    spec = SPEC_PATH.read_text(encoding="utf-8")

    # Build changed files block
    files_block = "\n".join(files)

    # Build constraint statements
    constraints = []
    if not has_src:
        constraints.append(
            "excluded types [feat, fix, refactor, perf, style], because no source code in changed paths."
        )
    if not has_test:
        constraints.append("excluded types [test], because no test files in changed paths.")
    constraints.append(f"commit type is limited to [{', '.join(sorted(allowed))}].")
    constraint_block = "\n".join(constraints)

    # Output formatted blocks
    block = f"{spec}"
    block += "\n```shell"
    block += f"\n$ {LIST_DIFF}\n{files_block}"
    block += f"\n$ {content_command}\n{diff}"
    block += "\n```\n"
    block += f"\n{constraint_block}\n"

    print(block)


if __name__ == "__main__":
    main()
