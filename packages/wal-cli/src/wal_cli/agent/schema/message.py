# packages/wal-cli/src/wal_cli/agent/schema/message.py

from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

from wal_runtime.schema import ErrorInfo


class Usage(BaseModel):
    input: int
    output: int
    context: int
    cached: int = 0


class ContentType(str, Enum):
    CALL = "call"
    TEXT = "text"


class BaseContent(BaseModel):
    pass


class ToolCallContent(BaseContent):
    block: Literal[ContentType.CALL] = ContentType.CALL
    id: str
    name: str
    arguments: type[BaseModel]


class TextContent(BaseContent):
    block: Literal[ContentType.TEXT] = ContentType.TEXT
    text: str


class MessageRole(str, Enum):
    QUERY = "query"
    REPLY = "reply"
    TOOL = "tool"


class BaseMessage(BaseModel):
    timestamp: int


class QueryMessage(BaseMessage):
    role: Literal[MessageRole.QUERY] = MessageRole.QUERY
    content: list[TextContent]


class ReplyMessage(BaseMessage):
    role: Literal[MessageRole.REPLY] = MessageRole.REPLY
    content: list[TextContent | ToolCallContent]
    usage: Usage


class ToolMessage(BaseMessage):
    role: Literal[MessageRole.TOOL] = MessageRole.TOOL
    call_id: str
    call_name: str
    content: list[TextContent]
    success: bool
    error: Optional[ErrorInfo]


Message = Annotated[Union[QueryMessage, ReplyMessage, ToolMessage], Field(discriminator="role")]
