# packages/wal-runtime/src/wal_runtime/pydantic_agent/hub.py

import json
import subprocess
from typing import Optional

from pydantic_ai import Agent, AgentSpec, ToolOutput

from wal_runtime.pydantic_agent.constants import AGENT_ROOT, AGENT_SPEC_SCHEMA_ROOT
from wal_runtime.pydantic_agent.util import get_model_infrastructure

from wal_runtime.util import WorkflowExecutor


def get_agent(identity: str) -> Agent:
    agent_spec_file = AGENT_ROOT / f"{identity}.spec.json"

    if not agent_spec_file.exists():
        raise ValueError(f"agent spec file {agent_spec_file} does not exist")

    agent_spec = AgentSpec.from_file(agent_spec_file)
    if agent_spec.model is None:
        raise ValueError(f"agent spec file {agent_spec_file} has no model")

    model, _ = get_model_infrastructure(agent_spec.model)
    return Agent.from_spec(agent_spec, model=model)


def init_agent_spec_file(identity: str, model: str):
    agent_spec_file = AGENT_ROOT / f"{identity}.spec.json"
    agent_spec_file.parent.mkdir(parents=True, exist_ok=True)
    agent_spec_schema_file = AGENT_SPEC_SCHEMA_ROOT / f"{identity}.schema.json"
    agent_spec_schema_file.parent.mkdir(parents=True, exist_ok=True)
    agent_spec = AgentSpec(model=model)
    agent_spec_schema_file.write_text(json.dumps(agent_spec.model_json_schema_with_capabilities()))
    agent_spec.to_file(agent_spec_file, fmt="json", schema_path=agent_spec_schema_file)


class PydanticAIWorkflowExecutor(WorkflowExecutor):
    def __init__(self, agent_identity: str):
        self.agent_identity = agent_identity
        self._agent = None  # Lazy loaded

    @property
    def agent(self):
        if self._agent is None:
            self._agent = get_agent(self.agent_identity)
        return self._agent

    def exec_shell(self, command: str, stdin: Optional[str] = None) -> tuple[str, bool]:
        try:
            result = subprocess.run(command, shell=True, input=stdin, text=True, capture_output=True, timeout=30)
            if result.returncode == 0:
                return result.stdout, True
            else:
                return result.stderr, False
        except subprocess.TimeoutExpired:
            return f"exec `{command}` timeout", False
        except Exception as e:
            return str(e), False

    def call_agent(self, message: str) -> str:
        try:
            result = self.agent.run_sync(message, output_type=ToolOutput(str))
            return result.output
        except Exception as e:
            return f"Error calling agent: {str(e)}"

    def ask_question(self, question: str) -> bool:
        try:
            # Create a tool call for the question
            result = self.agent.run_sync(question, output_type=ToolOutput(bool))
            # Extract the boolean result from the tool output
            return result.output
        except Exception:
            return False
