# packages/wal-cli/src/wal_cli/pydantic_agent/schema.py

import math
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, computed_field

from wal_cli.config.schema import ModelConfig


class ContextHealth(str, Enum):
    COMFORTABLE = "comfortable"  # token_usage < max_safe_token
    ELEVATED = "elevated"  # max_safe_token ≤ token_usage < max_limit_token
    CRITICAL = "critical"  # token_usage ≥ max_limit_token


class AgentDeps(BaseModel):
    agent_session_id: UUID
    model_info: ModelConfig

    @computed_field(description="Maximum context window length in tokens.")
    @property
    def max_context_length(self) -> int:
        return self.model_info.context_length

    @computed_field(description="Maximum limit context window length in tokens.")
    @property
    def max_limit_length(self) -> int:
        return self.max_context_length * 8 // 10

    @computed_field(description="Maximum safe context window length in tokens.")
    @property
    def max_safe_length(self) -> int:
        return self.max_context_length * 618 // 1000

    @computed_field(description="Limit chunk size in tokens.")
    @property
    def limit_chunk_size(self) -> int:
        return math.isqrt(self.max_limit_length)

    @computed_field(description="Safe chunk size in tokens.")
    @property
    def safe_chunk_size(self) -> int:
        return math.isqrt(self.max_safe_length)

    def get_context_health(self, current_token_usage: int) -> ContextHealth:
        if current_token_usage > self.max_limit_length:
            return ContextHealth.CRITICAL
        if current_token_usage > self.max_safe_length:
            return ContextHealth.ELEVATED
        return ContextHealth.COMFORTABLE
