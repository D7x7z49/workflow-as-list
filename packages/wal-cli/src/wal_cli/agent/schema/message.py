# packages/wal-cli/src/wal_cli/agent/schema/message.py

import json
from abc import ABC, abstractmethod
from enum import Enum
from typing import Annotated, Literal, Optional, Union, cast
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from anthropic.types.message_param import MessageParam
from anthropic.types.text_block_param import TextBlockParam
from anthropic.types.tool_use_block_param import ToolUseBlockParam
from anthropic.types.tool_result_block_param import ToolResultBlockParam
from anthropic.types.thinking_block_param import ThinkingBlockParam
from anthropic.types.redacted_thinking_block_param import RedactedThinkingBlockParam
from openai.types.chat import (
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionMessageToolCallParam,
)
from wal_cli.agent.schema.provider import ProviderInfo


class Usage(BaseModel):
    input: int
    output: int
    context: int
    cached: int = 0


class ContentType(str, Enum):
    CALL = "call"
    TEXT = "text"
    THINK = "think"


class TextContent(BaseModel):
    block: Literal[ContentType.TEXT] = ContentType.TEXT
    text: str

    def to_openai(self) -> ChatCompletionContentPartTextParam:
        return ChatCompletionContentPartTextParam(type="text", text=self.text)

    def to_anthropic(self) -> TextBlockParam:
        return TextBlockParam(type="text", text=self.text)


class ToolCallContent(BaseModel):
    block: Literal[ContentType.CALL] = ContentType.CALL
    id: str
    name: str
    arguments: str

    def to_openai(self) -> ChatCompletionMessageToolCallParam:
        return ChatCompletionMessageToolCallParam(
            id=self.id,
            type="function",
            function={
                "name": self.name,
                "arguments": self.arguments,
            },
        )

    def to_anthropic(self) -> ToolUseBlockParam:
        return ToolUseBlockParam(
            type="tool_use",
            id=self.id,
            name=self.name,
            input=json.loads(self.arguments) if self.arguments else {},
        )


class ThinkingContent(BaseModel):
    block: Literal[ContentType.THINK] = ContentType.THINK
    thinking: str
    thinkingSignature: Optional[str] = None
    redacted: Optional[bool] = None

    def to_openai(self) -> Union[str, None]:
        if self.redacted or self.thinkingSignature or not self.thinking:
            return None
        return self.thinking

    def to_anthropic(self) -> Union[TextBlockParam, ThinkingBlockParam, RedactedThinkingBlockParam, None]:
        if self.redacted:
            if not self.thinkingSignature:
                # redacted thinking requires thinkingSignature
                return None
            return RedactedThinkingBlockParam(type="redacted_thinking", data=self.thinkingSignature)

        if not self.thinking or not self.thinking.strip():
            # empty thinking content
            return None

        if not self.thinkingSignature or not self.thinkingSignature.strip():
            return TextBlockParam(type="text", text=self.thinking)

        return ThinkingBlockParam(type="thinking", thinking=self.thinking, signature=self.thinkingSignature)


class MessageRole(str, Enum):
    QUERY = "query"
    REPLY = "reply"
    TOOL = "tool"


class BaseMessage(BaseModel, ABC):
    timestamp: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))

    @abstractmethod
    def to_anthropic(self, info: ProviderInfo) -> MessageParam: ...

    @abstractmethod
    def to_openai(self, info: ProviderInfo) -> ChatCompletionMessageParam: ...


class QueryMessage(BaseMessage):
    role: Literal[MessageRole.QUERY] = MessageRole.QUERY
    content: list[TextContent]

    def to_openai(self, _) -> ChatCompletionMessageParam:
        return ChatCompletionUserMessageParam(role="user", content=[block.to_openai() for block in self.content])

    def to_anthropic(self, _) -> MessageParam:
        return MessageParam(role="user", content=[block.to_anthropic() for block in self.content])


class ReplyMessage(BaseMessage):
    role: Literal[MessageRole.REPLY] = MessageRole.REPLY
    content: list[TextContent | ToolCallContent | ThinkingContent]
    usage: Usage

    # model id, fommat: provider_name:model_name
    provider: str
    model: str

    # only openai fields
    refusal: Optional[str] = None

    def to_openai(self, info: ProviderInfo) -> ChatCompletionMessageParam:
        msg: dict = {"role": "assistant"}

        # text_blocks = [block.to_openai() for block in self.content if isinstance(block, TextContent)]
        # tool_calls = [block.to_openai() for block in self.content if isinstance(block, ToolCallContent)]
        # thinking = [block.to_openai() for block in self.content if isinstance(block, ThinkingContent)]
        # thinking = [block for block in thinking if block is not None]
        text_blocks = []
        tool_call_blocks = []
        thinking_blocks = []
        for block in self.content:
            if isinstance(block, TextContent):
                text_blocks.append(block.to_openai())
            elif isinstance(block, ToolCallContent):
                tool_call_blocks.append(block.to_openai())
            elif isinstance(block, ThinkingContent):
                data = block.to_openai()
                if data is None:
                    continue
                thinking_blocks.append(block.to_openai())

        if text_blocks:
            msg["content"] = text_blocks
        if tool_call_blocks:
            msg["tool_calls"] = tool_call_blocks
        if thinking_blocks:
            msg["reasoning_content"] = "\n".join(thinking_blocks)
        if self.refusal:
            msg["refusal"] = self.refusal
        return cast(ChatCompletionMessageParam, msg)

    def to_anthropic(self, info: ProviderInfo) -> MessageParam:
        content_blocks = [block.to_anthropic() for block in self.content]
        content_blocks = [block for block in content_blocks if block is not None]
        return MessageParam(role="assistant", content=content_blocks)


class ToolMessage(BaseMessage):
    role: Literal[MessageRole.TOOL] = MessageRole.TOOL
    call_id: str
    call_name: str
    content: list[TextContent]
    success: bool

    def to_openai(self, _) -> ChatCompletionMessageParam:
        return ChatCompletionToolMessageParam(
            role="tool",
            tool_call_id=self.call_id,
            content=[block.to_openai() for block in self.content],
        )

    def to_anthropic(self, _) -> MessageParam:
        return MessageParam(
            role="user",
            content=[
                ToolResultBlockParam(
                    type="tool_result",
                    tool_use_id=self.call_id,
                    content=[block.to_anthropic() for block in self.content],
                    is_error=(not self.success),
                )
            ],
        )


Message = Annotated[Union[QueryMessage, ReplyMessage, ToolMessage], Field(discriminator="role")]
