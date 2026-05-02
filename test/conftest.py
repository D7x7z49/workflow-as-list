# test/conftest.py
import pytest
from typing import Optional, Tuple

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
