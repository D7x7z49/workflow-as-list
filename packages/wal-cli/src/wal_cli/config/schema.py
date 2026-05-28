# packages/wal-cli/src/wal_cli/config/schema.py


from pydantic import Field

from wal_runtime.schema import RuntimeConfigProtocol

from wal_cli.agent.schema import AgentConfig, MemoryConfig, ProviderConfig


class RuntimeConfig(RuntimeConfigProtocol):
    providers: dict[str, ProviderConfig] = Field(..., description="The providers supported by the agent")
    memory: MemoryConfig

    @property
    def agent_config(self):
        return AgentConfig(
            providers=self.providers,
            memory=self.memory,
        )
