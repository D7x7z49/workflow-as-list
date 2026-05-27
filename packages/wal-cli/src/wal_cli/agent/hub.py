# packages/wal-cli/src/wal_cli/agent/hub.py

import shlex
import subprocess
from typing import Optional, Tuple
from pathlib import Path

from anthropic import transform_schema
from openai import OpenAI, pydantic_function_tool
from pydantic import BaseModel, Field
from wal_runtime.schema import ErrorInfo
from wal_runtime.util import WorkflowExecutor

from wal_cli.agent.schema import AgentConfig, AgentSpec
from wal_cli.agent.schema.message import Message, QueryMessage, ReplyMessage, TextContent, ToolCallContent, ToolMessage
from wal_cli.agent.util import LLM


SHELL_TOOL_NAME = "shell_exec"


class ShellArgument(BaseModel):
    """Input parameters for local shell command execution."""

    command: str = Field(description="shell command to execute")
    stdin: Optional[str] = Field(default=None, description="optional text piped to the command's stdin")
    cwd: Optional[str] = Field(default=None, description="working directory for the command")
    timeout: Optional[int] = Field(default=None, description="maximum execution time in seconds")


def exec_shell(args: ShellArgument) -> tuple[bool, str, str]:
    try:
        command = shlex.split(args.command)
        result = subprocess.run(
            command,
            input=args.stdin,
            cwd=args.cwd,
            timeout=args.timeout,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr
    except Exception as e:
        return False, "", ErrorInfo.from_exception(e).model_dump_json()


# Agent does not use generate_with_format because structured output is
# unstable across different LLM providers — this project adapts provider
# APIs directly without a dedicated abstraction layer, and its primary
# goal is validating the SYNTAX.ebnf concept.
class Agent(WorkflowExecutor):
    _OPENAI_SHELL_TOOL = pydantic_function_tool(ShellArgument, name=SHELL_TOOL_NAME)
    _ANTHROPIC_SHELL_TOOL = {
        "name": SHELL_TOOL_NAME,
        "description": "Execute a shell command and return success status, stdout, and stderr.",
        "input_schema": transform_schema(ShellArgument),
    }

    def __init__(self, spec: AgentSpec, config: AgentConfig):
        self.spec = spec
        self.config = config
        self.llm = LLM(spec.model, config)
        self._messages: list[Message] = []

    # -- class methods: stateless LLM helpers ------------------------------------

    @classmethod
    def _next(cls, llm: LLM, messages: list[Message], **kwargs) -> ReplyMessage:
        return llm.generate(messages, **kwargs)

    # -- instance: core reasoning loop ------------------------------------------

    def loop(self, message: str, /, *, memory: bool = False) -> str:
        if not memory:
            query = QueryMessage(content=[TextContent(text=message)])
            reply = self._next(self.llm, [query])
            text_blocks = [b for b in reply.content if isinstance(b, TextContent)]
            return text_blocks[0].text if text_blocks else ""

        self._messages.append(QueryMessage(content=[TextContent(text=message)]))
        max_iterations = 10

        for _ in range(max_iterations):
            tools = [self._OPENAI_SHELL_TOOL] if isinstance(self.llm.client, OpenAI) else [self._ANTHROPIC_SHELL_TOOL]
            reply = self._next(self.llm, self._messages, tools=tools)
            self._messages.append(reply)

            tool_calls = [b for b in reply.content if isinstance(b, ToolCallContent)]
            if not tool_calls:
                text_blocks = [b for b in reply.content if isinstance(b, TextContent)]
                return text_blocks[0].text if text_blocks else ""

            for tool_call in tool_calls:
                if tool_call.name != SHELL_TOOL_NAME:
                    continue
                try:
                    args = ShellArgument.model_validate_json(tool_call.arguments)
                except Exception:
                    self._messages.append(
                        ToolMessage(
                            call_id=tool_call.id,
                            call_name=tool_call.name,
                            content=[TextContent(text="invalid arguments")],
                            success=False,
                        )
                    )
                    continue
                success, stdout, stderr = exec_shell(args)
                result_text = stdout
                if stderr:
                    result_text = f"{stdout}\n{stderr}" if stdout else stderr
                self._messages.append(
                    ToolMessage(
                        call_id=tool_call.id,
                        call_name=tool_call.name,
                        content=[TextContent(text=result_text)],
                        success=success,
                    )
                )

        return ""

    # -- WorkflowExecutor interface ---------------------------------------------

    def exec_shell(self, command: str, stdin: Optional[str] = None) -> Tuple[str, bool]:
        args = ShellArgument(command=command, stdin=stdin, cwd=Path.cwd().as_posix())
        success, stdout, stderr = exec_shell(args)
        output = stdout
        if stderr:
            output = f"{stdout}\n{stderr}" if stdout else stderr
        self._messages.append(
            QueryMessage(content=[TextContent(text=(f"Command: {command}\nSuccess: {success}\nOutput:\n{output}"))])
        )
        return output, success

    def ask_question(self, question: str) -> bool:
        result = self.loop(f"Answer only 'yes' or 'no':\n{question}")
        return result.strip().lower().startswith("yes")

    def call_agent(self, message: str) -> str:
        return self.loop(message, memory=self.config.memory.enabled)
