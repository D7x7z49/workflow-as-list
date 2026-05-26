# test/conftest.py
import hashlib
import os
from typing import Optional, Tuple

import pytest

from wal_core.schema import ImportPathAdapter, WorkflowModule
from wal_runtime.schema import WhiteList
from wal_runtime.util import WorkflowExecutor
from wal_cli.agent.schema import AgentConfig, MemoryConfig
from wal_cli.agent.schema.provider import (
    ModelConfig,
    ModelContextInfo,
    OpenAICompatibleProvider,
    ProviderAdapter,
    ProviderConfig,
)
from wal_cli.agent.util import LLM
from wal_cli.config.schema import RuntimeConfig


# ============================================================================
# test doubles
# ============================================================================


class FakeWorkflowExecutor(WorkflowExecutor):
    def __init__(self):
        self.shell_commands: list[tuple[str, Optional[str]]] = []
        self.questions: list[str] = []
        self.agent_calls: list[str] = []
        self.shell_responses: dict[str, tuple[str, bool]] = {}
        self.question_responses: dict[str, bool] = {}
        self.agent_responses: dict[str, str] = {}

    def exec_shell(self, command: str, stdin: Optional[str] = None) -> Tuple[str, bool]:
        self.shell_commands.append((command, stdin))
        resp = self.shell_responses.get(command, ("", True))
        return resp

    def ask_question(self, question: str) -> bool:
        self.questions.append(question)
        return self.question_responses.get(question, True)

    def call_agent(self, message: str) -> str:
        self.agent_calls.append(message)
        return self.agent_responses.get(message, "fake response")


@pytest.fixture
def fake_executor():
    return FakeWorkflowExecutor()


# ============================================================================
# runtime config (used by wal_runtime tests)
# ============================================================================


@pytest.fixture
def config():
    return RuntimeConfig(
        white_list=WhiteList(domain=[], command=[]),
        providers={},
        memory=MemoryConfig(enabled=False),
    )


# ============================================================================
# shared helpers (module factory, workspace)
# ============================================================================


def make_module(name: str, namespace: Optional[str] = None) -> WorkflowModule:
    if namespace is None:
        namespace = hashlib.sha256(name.encode()).hexdigest()
    else:
        # ensure it's 64 hex digits
        if len(namespace) != 64 or not all(c in "0123456789abcdefABCDEF" for c in namespace):
            namespace = hashlib.sha256(name.encode()).hexdigest()
    return WorkflowModule(
        path=ImportPathAdapter.validate_python(f"file:///{name}"),
        namespace=namespace,
    )


@pytest.fixture
def module_factory():
    return make_module


@pytest.fixture
def workspace(tmp_path):
    """Provide a temporary workspace root for WorkflowRuntime."""
    return tmp_path


# ============================================================================
# agent config builders (reusable across LLM provider tests)
# ============================================================================


def _build_agent_config(provider: ProviderConfig, *, provider_id: str = "test") -> AgentConfig:
    """Wrap a single ProviderConfig into an AgentConfig.

    The agent config derives the same shape as RuntimeConfig.agent_config,
    reused across all LLM provider fixtures.

    Args:
        provider: The provider configuration (OpenAICompatible, DeepSeek, etc.).
        provider_id: Key name for the provider in the providers dict.

    Returns:
        AgentConfig with the given provider and memory disabled.
    """
    return AgentConfig(
        providers={provider_id: provider},
        memory=MemoryConfig(enabled=False),
    )


def _build_test_llm(agent_config: AgentConfig, *, identity: str) -> LLM:
    """Build an LLM instance from an AgentConfig.

    Thin factory so every provider fixture follows the same
    AgentConfig → LLM path.
    """
    return LLM(identity=identity, config=agent_config)


# ============================================================================
# LLM provider fixtures
# ============================================================================


@pytest.fixture
def openai_compatible_llm():
    """Provide an LLM instance configured for an OpenAI-compatible API.

    Env vars: TEST_OPENAI_BASE_URL, TEST_OPENAI_API_KEY, TEST_OPENAI_MODEL.
    Skips the test if any variable is missing.
    """
    base_url = os.environ.get("TEST_OPENAI_BASE_URL")
    api_key = os.environ.get("TEST_OPENAI_API_KEY")
    model = os.environ.get("TEST_OPENAI_MODEL")

    if base_url is None or api_key is None or model is None:
        pytest.skip("TEST_OPENAI_BASE_URL, TEST_OPENAI_API_KEY, TEST_OPENAI_MODEL environment variables are required")

    provider = OpenAICompatibleProvider(
        adapter=ProviderAdapter.OPENAI_COMPATIBLE,
        base_url=base_url,
        api_key=api_key,
        models={
            model: ModelConfig(
                context=ModelContextInfo(max_tokens=4096),
            )
        },
    )

    agent_config = _build_agent_config(provider)
    return _build_test_llm(agent_config, identity=f"test:{model}")
