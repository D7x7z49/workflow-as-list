# packages/wal-cli/src/wal_cli/config/hub.py

import json
import threading
from functools import lru_cache

from wal_cli.config.constants import CONFIG_FILE, CONFIG_SCHEMA_FILE, DEFAULT_CONFIG_DATA
from wal_cli.config.schema import RuntimeConfig


_load_lock = threading.Lock()


@lru_cache(maxsize=1)
def load_config() -> RuntimeConfig:
    with open(CONFIG_FILE, "r") as f:
        config_data = json.load(f)
    return RuntimeConfig(**config_data)


def reload_config() -> RuntimeConfig:
    with _load_lock:
        load_config.cache_clear()
        return load_config()


def init_config():
    if not CONFIG_FILE.exists():
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG_DATA, f, indent=2)

    schema = RuntimeConfig.model_json_schema()
    CONFIG_SCHEMA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_SCHEMA_FILE, "w") as f:
        json.dump(schema, f, indent=2)
