# packages/wal-cli/src/wal_cli/config/constants.py

from os import environ
from pathlib import Path

ROOT = Path(environ.get("WAL_HOME", Path.home())) / ".wal"
CONFIG_FILE = ROOT / "config.json"

SCHEMA_ROOT = ROOT / "schema"
CONFIG_SCHEMA_FILE = SCHEMA_ROOT / "config.schema.json"

CACHE_ROOT = ROOT / "cache"

DATA_ROOT = ROOT / "data"

RUNS_ROOT = DATA_ROOT / "runs"
RUNS_MAP_FILE = RUNS_ROOT / "runs_map.jsonl"

AGENT_ROOT = ROOT / "agent"
AGENT_SPEC_SCHEMA_FILE = SCHEMA_ROOT / "agent.schema.json"

DEFAULT_CONFIG_DATA = {
    "$schema": CONFIG_SCHEMA_FILE.as_uri(),
    "memory": {"enabled": True},
    "white_list": {
        "domain": [],
        "command": [],
    },
    "providers": {},
}
