# test/conftest.py
import pytest
import hashlib
from typing import Optional, Tuple

from waf_core.schema import WorkflowModule, ImportPathAdapter
from waf_runtime.config.schema import RuntimeConfig, WhiteList
from waf_runtime.util import WorkflowExecutor


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


@pytest.fixture
def config():
    return RuntimeConfig(white_list=WhiteList(domain=[], command=[]), providers={})


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
