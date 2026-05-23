# packages/wal-cli/src/wal_cli/agent/hub.py


from typing import Tuple


from wal_runtime.util import WorkflowExecutor

from wal_cli.agent.schema import AgentConfig, AgentEnvironmentInfo, AgentSpec


class AgentEnvironment:
    def __init__(self, info: AgentEnvironmentInfo):
        self.info = info


class LLM:
    def __init__(self, identity: str, config: AgentConfig):
        self.identity = identity

        provider_id, model_id = identity.split(":", 1)
        self.config = config
        self.provider_id = provider_id
        self.provider = config.providers[self.provider_id]
        self.model_id = model_id
        self.model = self.provider.models[self.model_id]

        self.client = self.provider.get_client()


class Agent(WorkflowExecutor):
    def __init__(self, spec: AgentSpec, config: AgentConfig):
        self.llm = LLM(spec.model, config)

    def exec_shell(self, command: str, stdin: str | None = None) -> Tuple[str, bool]:
        raise NotImplementedError

    def ask_question(self, question: str) -> bool:
        raise NotImplementedError

    def call_agent(self, message: str) -> str:
        raise NotImplementedError


if __name__ == "__main__":
    from wal_cli.config.hub import init_config, load_config

    init_config()

    config = load_config()
    agent = LLM("deepseek:deepseek-chat", config.agent_config)
