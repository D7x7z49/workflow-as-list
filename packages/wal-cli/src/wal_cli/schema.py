# packages/wal-cli/src/wal_cli/schema.py

from pydantic import BaseModel

from wal_runtime.config.schema import RuntimeConfig


class CommandContext(BaseModel):
    config: RuntimeConfig
