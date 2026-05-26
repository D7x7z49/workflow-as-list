# packages/wal-cli/src/wal_cli/agent/schema/message.py

import json
from abc import ABC, abstractmethod
from enum import Enum
from typing import Annotated, Literal, Optional, Union
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from anthropic.types.message_param import MessageParam
from anthropic.types.text_block_param import TextBlockParam
from anthropic.types.tool_use_block_param import ToolUseBlockParam
from anthropic.types.tool_result_block_param import ToolResultBlockParam
from openai.types.chat import (
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionAssistantMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionMessageToolCallParam,
)


class Usage(BaseModel):
    input: int
    output: int
    context: int
    cached: int = 0


class ContentType(str, Enum):
    CALL = "call"
    TEXT = "text"


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


class MessageRole(str, Enum):
    QUERY = "query"
    REPLY = "reply"
    TOOL = "tool"


class BaseMessage(BaseModel, ABC):
    timestamp: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))

    @abstractmethod
    def to_anthropic(self) -> MessageParam: ...

    @abstractmethod
    def to_openai(self) -> ChatCompletionMessageParam: ...


class QueryMessage(BaseMessage):
    role: Literal[MessageRole.QUERY] = MessageRole.QUERY
    content: list[TextContent]

    def to_openai(self) -> ChatCompletionMessageParam:
        return ChatCompletionUserMessageParam(role="user", content=[block.to_openai() for block in self.content])

    def to_anthropic(self) -> MessageParam:
        return MessageParam(role="user", content=[block.to_anthropic() for block in self.content])


class ReplyMessage(BaseMessage):
    role: Literal[MessageRole.REPLY] = MessageRole.REPLY
    content: list[TextContent | ToolCallContent]
    usage: Usage

    # model id, fommat: provider_name:model_name
    model: str

    # only openai fields
    refusal: Optional[str] = None

    def to_openai(self) -> ChatCompletionMessageParam:
        text_blocks = [block.to_openai() for block in self.content if isinstance(block, TextContent)]
        tool_calls = [block.to_openai() for block in self.content if isinstance(block, ToolCallContent)]

        msg = ChatCompletionAssistantMessageParam(
            role="assistant",
            content=text_blocks if text_blocks else None,
            refusal=self.refusal,
        )

        if tool_calls:
            msg["tool_calls"] = tool_calls
        if self.refusal:
            msg["refusal"] = self.refusal
        return msg

    def to_anthropic(self) -> MessageParam:
        content_blocks = [block.to_anthropic() for block in self.content]
        return MessageParam(role="assistant", content=content_blocks)


class ToolMessage(BaseMessage):
    role: Literal[MessageRole.TOOL] = MessageRole.TOOL
    call_id: str
    call_name: str
    content: list[TextContent]
    success: bool

    def to_openai(self) -> ChatCompletionMessageParam:
        return ChatCompletionToolMessageParam(
            role="tool",
            tool_call_id=self.call_id,
            content=[block.to_openai() for block in self.content],
        )

    def to_anthropic(self) -> MessageParam:
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
