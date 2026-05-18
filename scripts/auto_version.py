# scripts/auto_version.py

import re
import tomllib
import argparse
import subprocess
from pathlib import Path
from dataclasses import dataclass, field

CONFIG_FILE = ".auto-version.config.toml"
CONFIG_PATH = Path.cwd() / CONFIG_FILE
CHANGELOG_PATH = Path.cwd() / "CHANGELOG.md"
DEFAULT_VERSION = "0.1.0"

RE_CONVENTIONAL = re.compile(
    r"^(?P<type>[a-zA-Z][-a-zA-Z]*)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<breaking>!)?: "
    r"(?P<desc>.+)$"
)

RE_SEMVER = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?P<pre>[a-zA-Z]+\w*)?$"
)

OUTPUT_TEXT = []


@dataclass
class Config:
    projects: list[str] = field(default_factory=list)
    major: list[str] = field(default_factory=list)
    minor: list[str] = field(default_factory=list)
    patch: list[str] = field(default_factory=list)
    release_branch: str = field(default="main")

    # fix deps table
    fix_deps_repo_url: str | None = field(default=None)

    @classmethod
    def from_path(cls, path: Path) -> "Config":
        try:
            with open(path, "rb") as fh:
                raw = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            exit(f"[!] Invalid TOML in {CONFIG_FILE}: {exc}")

        data = cls()
        required = ["projects", "major", "minor", "patch"]
        for key in required:
            if key not in raw:
                exit(f"[!] Missing required key '{key}' in {CONFIG_FILE}")
            if not isinstance(raw[key], list):
                exit(f"[!] '{key}' must be a list in {CONFIG_FILE}")
            setattr(data, key, raw[key])

        fix_deps_table = raw.get("fix-deps")
        if fix_deps_table and isinstance(fix_deps_table, dict):
            repo_url = fix_deps_table.get("repo-url")
            if not repo_url or not isinstance(repo_url, str):
                exit(f"[!] 'fix-deps.repo-url' must be a string in {CONFIG_FILE}")
            data.fix_deps_repo_url = repo_url

        optional = ["release_branch"]
        for key in optional:
            if key in raw:
                if not isinstance(raw[key], str):
                    exit(f"[!] '{key}' must be a string in {CONFIG_FILE}")
                setattr(data, key, raw[key])

        return data


@dataclass
class ReleaseInfo:
    name: str
    path: Path
    new_version: str | None
    old_version: str | None


def ensure_clean_workspace(config: Config) -> None:
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        exit("[!] working directory is not clean, please commit or stash changes first")

    result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    if result.stdout.strip() != config.release_branch:
        exit(f"[!] not on release branch <{config.release_branch}>, current branch is <{result.stdout.strip()}>")


def get_package_name(proj_path: Path) -> str:
    toml = proj_path / "pyproject.toml"
    if not toml.exists():
        exit(f"[!] {toml} not found")
    with open(toml, "rb") as f:
        data = tomllib.load(f)
    if "project" not in data or "name" not in data["project"]:
        exit(f"[!] [project].name missing in {toml}")
    return data["project"]["name"]


def is_safe_str(s: str) -> None:
    if not re.match(r"^[a-zA-Z0-9_-]+$", s) and len(s) < 36:
        exit(f"[!] package <{s}> is not valid")


def get_last_tag(package_name: str) -> tuple[str | None, str | None]:
    cmd = ["git", "tag", "--list", f"{package_name}-v*", "--sort=-version:refname"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        exit(f"[!] git tag failed:\n{result.stderr.strip()}")
    lines = result.stdout.strip().splitlines()
    if not lines:
        return None, None
    tag = lines[0]
    version = tag.removeprefix(f"{package_name}-v")
    return tag, version


def get_commits_since(tag: str) -> list[tuple[str, str]]:
    cmd = ["git", "log", "--first-parent", f"{tag}..HEAD", "--reverse", "--pretty=format:%h %s"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        exit(f"[!] git log failed:\n{result.stderr.strip()}")
    lines = result.stdout.strip().splitlines()
    if not lines:
        return []

    commits = []
    for line in lines:
        hash, message = line.split(" ", 1)
        is_safe_str(hash)
        commits.append((hash, message))
    return commits


def parse_version(version: str) -> tuple[int, int, int, str | None]:
    match = RE_SEMVER.match(version)
    if not match:
        exit(f"[!] invalid version: {version}")
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    pre = match.group("pre")
    return major, minor, patch, pre


def is_package_commit(hash: str, path: str | Path) -> bool:
    cmd = ["git", "show", "--first-parent", hash, "--name-only", "--pretty=format:"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False
    lines = result.stdout.strip().splitlines()
    if not lines:
        return False
    for line in lines:
        if line.startswith(f"{path}/"):
            return True
    return False


def classify_commit(subject: str, config: Config) -> str | None:
    match = RE_CONVENTIONAL.match(subject)
    if not match:
        return None
    typ = match.group("type")
    breaking = match.group("breaking") is not None
    if breaking and typ in config.major:
        return "major"
    if not breaking and typ in config.minor:
        return "minor"
    if not breaking and typ in config.patch:
        return "patch"
    return None


def compute_bump(config: Config, path: str | Path, tag: str, version: str, stage: str) -> str:
    major, minor, patch, pre = parse_version(version)
    commits = get_commits_since(tag)
    if not commits:
        return version

    is_changed = False
    for hash, subject in commits:
        if not is_package_commit(hash, path):
            continue
        bump = classify_commit(subject, config)
        if not bump:
            continue

        OUTPUT_TEXT.append(f"[+] <{hash}> <{bump}>")
        is_changed = True
        match bump:
            case "major":
                major, minor, patch = major + 1, 0, 0
            case "minor":
                minor, patch = minor + 1, 0
            case "patch":
                patch = patch + 1

    if not is_changed:
        return version

    num = None
    if pre and stage in ("alpha", "beta", "rc"):
        if pre.startswith("alpha"):
            num = int(pre[5:])
        if pre.startswith("beta"):
            num = int(pre[4:])
        if pre.startswith("rc"):
            num = int(pre[2:])

    match stage:
        case "stable":
            pre = None
        case "dev":
            pre = f"dev{commits[-1][0]}"
        case "alpha" | "beta" | "rc":
            pre = f"{stage}1" if pre is None or num is None else f"{stage}{num + 1}"

    if pre:
        new_version = f"{major}.{minor}.{patch}{pre}"
    else:
        new_version = f"{major}.{minor}.{patch}"
    return new_version


def update_pyproject_file(info: ReleaseInfo, dry_run: bool, deps_map: dict[str, str] | None = None) -> None:
    toml_path = info.path / "pyproject.toml"
    lines = toml_path.read_text().splitlines()
    status = None
    new_lines = []

    for line in lines:
        stripped = line.strip()
        comment = ""
        if "#" in line:
            # split at first # and preserve the comment part
            code_part, comment = line.split("#", 1)
            stripped = code_part.strip()
        else:
            code_part = line

        # detect table header
        if stripped.startswith("[") and stripped.endswith("]"):
            status = None
            if stripped == "[project]":
                status = "project"
            new_lines.append(line)
            continue

        # inside [project]
        if status == "project":
            if stripped.startswith("version") and info.new_version:
                new_line = f'version = "{info.new_version}"'
                if comment:
                    new_line += f" # {comment}"
                new_lines.append(new_line)
                continue
            if stripped.startswith("dependencies"):
                status = "dependencies" if deps_map else None
                new_lines.append(line)
                continue

        # inside dependencies list
        if status == "dependencies" and deps_map:
            if stripped == "]":
                status = None
                new_lines.append(line)
                continue

            s = stripped.find('"')
            e = stripped.rfind('"')
            if s == -1 or e == -1:
                new_lines.append(line)
                continue

            dep = stripped[s + 1 : e]
            dep_name = dep.split("@", 1)[0].strip() if "@" in dep else dep

            if dep_name in deps_map:
                # preserve indentation
                i = code_part.find('"')
                insert = code_part[:i]
                new_line = f'{insert}"{dep_name} @ {deps_map[dep_name]}"'
                # preserve trailing comma if present
                if code_part.rstrip().endswith(","):
                    new_line += ","
                if comment:
                    new_line += f" # {comment}"
                new_lines.append(new_line)
                continue

        new_lines.append(line)

    new_content = "\n".join(new_lines) + "\n"

    if not dry_run:
        toml_path.write_text(new_content)
    OUTPUT_TEXT.append(f"[+] updated <{toml_path}>")


def release_changes(items: list[ReleaseInfo], dry_run: bool) -> None:
    released = [info for info in items if info.new_version is not None]
    if not released:
        OUTPUT_TEXT.append("[?] no changes detected")
        return

    msg = ["chore(release): auto update project version"]
    for info in released:
        if info.old_version:
            msg.append(f"- bump {info.name} from {info.old_version} to {info.new_version}")
        else:
            msg.append(f"- release {info.name} at {info.new_version}")
    msg = "\n".join(msg)
    if not dry_run:
        subprocess.run(["git", "add", "."], check=True)
        status = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if status.returncode != 0:
            subprocess.run(["git", "commit", "-m", msg], check=True)
        else:
            exit("[!] nothing to commit")
    OUTPUT_TEXT.append("[+] commit successful")

    for info in released:
        if not dry_run:
            subprocess.run(["git", "tag", f"{info.name}-v{info.new_version}"], check=True)
        OUTPUT_TEXT.append(f"[+] <{info.name}-v{info.new_version}>")


def main():
    if CONFIG_PATH.exists():
        OUTPUT_TEXT.append(f"[+] use <{CONFIG_FILE}> as config")
    else:
        exit(f"[!] missing <{CONFIG_FILE}>")

    parser = argparse.ArgumentParser(description="Auto version bump based on Conventional Commits")
    parser.add_argument(
        "--stage",
        choices=["stable", "alpha", "beta", "rc", "dev"],
        default="stable",
        help="Release stage (default: stable)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done, no changes")
    parser.add_argument("--quiet", action="store_true", help="Suppress informational output")
    args = parser.parse_args()

    OUTPUT_TEXT.append(f"[-] load config from <{CONFIG_FILE}>")
    config = Config.from_path(CONFIG_PATH)
    if not args.dry_run:
        ensure_clean_workspace(config)

    OUTPUT_TEXT.append("[-] get package name")
    projects: list[tuple[str, Path]] = [(get_package_name(Path(proj)), Path(proj)) for proj in config.projects]
    for name, path in projects:
        is_safe_str(name)
        OUTPUT_TEXT.append(f"[+] <{name}> at [{path}]")

    OUTPUT_TEXT.append("[-] get now version")
    changed: list[ReleaseInfo] = []
    for name, path in projects:
        changed.append(ReleaseInfo(name, path, None, None))
        tag, version = get_last_tag(name)
        if tag and version:
            OUTPUT_TEXT.append(f"[+] <{name}> at {tag}")
            changed[-1].old_version = version
            new_version = compute_bump(config, path, tag, version, args.stage)
            if changed[-1].old_version != new_version:
                OUTPUT_TEXT.append(f"[+] <{name}> bump to {new_version}")
                changed[-1].new_version = new_version
            else:
                OUTPUT_TEXT.append(f"[?] <{name}> unchanged")
        else:
            OUTPUT_TEXT.append(f"[?] <{name}> no tag, set <{DEFAULT_VERSION}> (first release)")
            changed[-1].new_version = DEFAULT_VERSION
            if not args.dry_run:
                CHANGELOG_PATH.touch(exist_ok=True)

    OUTPUT_TEXT.append("[-] update version")
    if config.fix_deps_repo_url:
        url = config.fix_deps_repo_url
        deps_map = {}
        for info in changed:
            version = info.new_version if info.new_version else info.old_version
            deps_map[info.name] = f"git+{url}@{info.name}-v{version}#subdirectory={info.path}"
    for info in changed:
        if config.fix_deps_repo_url and deps_map:
            update_pyproject_file(info, args.dry_run, deps_map)
        else:
            update_pyproject_file(info, args.dry_run)
    if not args.dry_run:
        subprocess.run(["uv", "lock"], check=True)

    OUTPUT_TEXT.append("[-] commit changes and tags")
    release_changes(changed, args.dry_run)

    if not args.quiet:
        print("\n".join(OUTPUT_TEXT))


if __name__ == "__main__":
    main()
