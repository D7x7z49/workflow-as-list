# test/wal_cli/agent/test_util_llm.integration.test.py
"""Integration tests for LLM.generate via OpenAI and Anthropic APIs.

OpenAI-compatible requires:
- TEST_OPENAI_BASE_URL
- TEST_OPENAI_API_KEY
- TEST_OPENAI_MODEL

Anthropic-compatible requires:
- TEST_ANTHROPIC_BASE_URL
- TEST_ANTHROPIC_API_KEY
- TEST_ANTHROPIC_MODEL
"""

from anthropic import transform_schema
from openai import pydantic_function_tool
from pydantic import BaseModel, Field

from wal_cli.agent.schema.message import (
    QueryMessage,
    ReplyMessage,
    TextContent,
    ToolCallContent,
    ToolMessage,
)


class CalculatorParams(BaseModel):
    """Add two integers and return the sum."""

    a: int = Field(description="Left operand of binary addition")
    b: int = Field(description="Right operand of binary addition")


OPENAI_CALCULATOR_TOOL = pydantic_function_tool(CalculatorParams, name="calculator")

ANTHROPIC_CALCULATOR_TOOL = {
    "name": "calculator",
    "description": "Add two integers and return the sum.",
    "input_schema": transform_schema(CalculatorParams),
}


def _assert_reply(reply, expected_type):
    """Assert reply is ReplyMessage with at least one block of expected type."""
    assert isinstance(reply, ReplyMessage)
    assert len(reply.content) > 0
    # some models emit text alongside tool calls; check existence, not exclusivity
    assert any(isinstance(block, expected_type) for block in reply.content)


def _compute_calculator_result(tool_call: ToolCallContent) -> int:
    """Parse calculator tool arguments and return the sum."""

    calculator = CalculatorParams.model_validate_json(tool_call.arguments)
    return calculator.a + calculator.b


class TestLLMOpenAIGenerate:
    """Round-trip integration tests for LLM.generate via OpenAI-compatible API."""

    def test_two_round_tool_call(self, openai_compatible_llm):
        """Two-round conversation: request tool call, then return tool result."""
        query = QueryMessage(content=[TextContent(text="Use the calculator tool to compute 2+2.")])
        reply1 = openai_compatible_llm.generate([query], tools=[OPENAI_CALCULATOR_TOOL])

        _assert_reply(reply1, ToolCallContent)

        assert reply1.usage is not None
        assert reply1.usage.input > 0
        assert reply1.usage.output > 0

        tool_call = next(block for block in reply1.content if isinstance(block, ToolCallContent))
        assert tool_call.name == "calculator"

        result = _compute_calculator_result(tool_call)

        tool_msg = ToolMessage(
            call_id=tool_call.id,
            call_name=tool_call.name,
            content=[TextContent(text=str(result))],
            success=True,
        )
        messages = [query, reply1, tool_msg]
        reply2 = openai_compatible_llm.generate(messages)

        _assert_reply(reply2, TextContent)

        final_text = reply2.content[0].text
        assert "4" in final_text, f"Expected '4' in final reply, got: {final_text}"

        assert reply2.usage is not None
        assert reply2.usage.input > 0
        assert reply2.usage.output > 0


class TestLLMAnthropicGenerate:
    """Round-trip integration tests for LLM.generate via Anthropic-compatible API."""

    def test_two_round_tool_call(self, anthropic_compatible_llm):
        """Two-round conversation: request tool call, then return tool result."""
        query = QueryMessage(content=[TextContent(text="Use the calculator tool to compute 2+2.")])
        reply1 = anthropic_compatible_llm.generate([query], tools=[ANTHROPIC_CALCULATOR_TOOL], max_tokens=1024)

        _assert_reply(reply1, ToolCallContent)

        assert reply1.usage is not None
        assert reply1.usage.input > 0
        assert reply1.usage.output > 0

        tool_call = next(block for block in reply1.content if isinstance(block, ToolCallContent))
        assert tool_call.name == "calculator"

        result = _compute_calculator_result(tool_call)

        tool_msg = ToolMessage(
            call_id=tool_call.id,
            call_name=tool_call.name,
            content=[TextContent(text=str(result))],
            success=True,
        )
        messages = [query, reply1, tool_msg]
        reply2 = anthropic_compatible_llm.generate(messages, max_tokens=1024)

        _assert_reply(reply2, TextContent)

        final_text = reply2.content[0].text
        assert "4" in final_text, f"Expected '4' in final reply, got: {final_text}"

        assert reply2.usage is not None
        assert reply2.usage.input > 0
        assert reply2.usage.output > 0
