# test/wal_cli/agent/test_llm_openai.integration.test.py
"""Integration tests for LLM.generate via OpenAI-compatible API.

Requires environment variables:
- TEST_OPENAI_BASE_URL
- TEST_OPENAI_API_KEY
- TEST_OPENAI_MODEL
"""

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


CALCULATOR_TOOL = pydantic_function_tool(CalculatorParams, name="calculator")


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
    """Round-trip integration tests for LLM.generate over real API."""

    def test_two_round_tool_call(self, openai_compatible_llm):
        """Two-round conversation: request tool call, then return tool result."""
        # Round 1: ask model to call calculator tool for 2+2
        query = QueryMessage(content=[TextContent(text="Use the calculator tool to compute 2+2.")])
        reply1 = openai_compatible_llm.generate([query], tools=[CALCULATOR_TOOL])

        _assert_reply(reply1, ToolCallContent)

        # gather usage from round 1
        assert reply1.usage is not None
        assert reply1.usage.input > 0
        assert reply1.usage.output > 0

        # extract the first tool call (some models also emit text blocks)
        tool_call = next(block for block in reply1.content if isinstance(block, ToolCallContent))
        assert isinstance(tool_call, ToolCallContent)
        assert tool_call.name == "calculator"

        result = _compute_calculator_result(tool_call)

        # Round 2: send tool result back
        tool_msg = ToolMessage(
            call_id=tool_call.id,
            call_name=tool_call.name,
            content=[TextContent(text=str(result))],
            success=True,
        )
        messages = [query, reply1, tool_msg]
        reply2 = openai_compatible_llm.generate(messages)

        # model should now reply with text content
        _assert_reply(reply2, TextContent)

        # final reply should mention the result
        final_text = reply2.content[0].text
        assert "4" in final_text, f"Expected '4' in final reply, got: {final_text}"

        # usage for round 2
        assert reply2.usage is not None
        assert reply2.usage.input > 0
        assert reply2.usage.output > 0
