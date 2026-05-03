# packages/waf-cli/src/waf_cli/schema.py

from pydantic import BaseModel

from waf_runtime.config.schema import RuntimeConfig


class CommandContext(BaseModel):
    config: RuntimeConfig
