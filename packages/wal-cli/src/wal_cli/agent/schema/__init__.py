# packages/wal-cli/src/wal_cli/agent/schema/__init__.py

import json
from uuid import UUID
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from wal_cli.agent.schema.message import (
    Usage,
    ContentType,
    ToolCallContent,
    TextContent,
    MessageRole,
    BaseMessage,
    QueryMessage,
    ReplyMessage,
    ToolMessage,
    Message,
)
from wal_cli.agent.schema.provider import (
    ModelContextInfo,
    ModelConfig,
    ProviderAdapter,
    ProviderConfig,
)


__all__ = [
    "Usage",
    "ContentType",
    "ToolCallContent",
    "TextContent",
    "MessageRole",
    "BaseMessage",
    "QueryMessage",
    "ReplyMessage",
    "ToolMessage",
    "Message",
    "ModelContextInfo",
    "ModelConfig",
    "ProviderAdapter",
    "ProviderConfig",
]


class MemoryConfig(BaseModel):
    enabled: bool = Field(..., description="Enable memory")


class AgentConfig(BaseModel):
    providers: dict[str, ProviderConfig]
    memory: MemoryConfig


class AgentSpec(BaseModel):
    id: UUID
    name: str
    model: str  # fomat: "provider:model"

    @staticmethod
    def from_json_file(file_path: Path) -> "AgentSpec":
        data = json.loads(file_path.read_text())
        return AgentSpec.model_validate(data)

    @staticmethod
    def from_json_file_by_name(name: str, agent_dir: Path) -> Optional["AgentSpec"]:
        for spec_file in agent_dir.glob("*.agent.json"):
            spec = AgentSpec.from_json_file(spec_file)
            if spec.name == name:
                return spec
        return None

    def to_json_file(self, agent_dir: Path, schema_path: Path) -> Path:
        schema_path.write_text(json.dumps(AgentSpec.model_json_schema(), indent=2, ensure_ascii=False))
        agent_dir.mkdir(parents=True, exist_ok=True)
        file_path = agent_dir / f"{self.id}.agent.json"
        data = {
            "$schema": schema_path.as_uri(),
            **self.model_dump(mode="json"),
        }
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return file_path


# SSH URL FORMAT: ssh://username@hostname:port#path
# SSH URL only identify host and must use identity file, DON'T USE PASSWORD.
# path is working directory, path must be absolute.
class AgentEnvironmentInfo(BaseModel):
    username: str
    hostname: str
    port: int
    path: str

    @property
    def ssh_url(self):
        return f"ssh://{self.username}@{self.hostname}:{self.port}#{self.path}"
