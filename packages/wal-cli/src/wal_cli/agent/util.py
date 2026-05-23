# packages/wal-cli/src/wal_cli/agent/util.py

from anthropic import Anthropic
from openai import OpenAI

from pydantic import BaseModel
from wal_cli.agent.schema.message import Message, ReplyMessage
from wal_cli.agent.schema.provider import ProviderAdapter


def transform_messages_to_openai(messages: list[Message]) -> list[dict]: ...
def transform_messages_to_anthropic(messages: list[Message]) -> tuple[list[dict], str | None]: ...


def reply_from_openai(response) -> ReplyMessage: ...
def reply_from_anthropic(response) -> ReplyMessage: ...


def generate_by_openai(
    client: OpenAI,
    adapter: ProviderAdapter,
    messages: list[Message],
    tools: list[type[BaseModel]] | None = None,
    **kwargs,
) -> ReplyMessage: ...


def generate_by_anthropic(
    client: Anthropic,
    adapter: ProviderAdapter,
    messages: list[Message],
    tools: list[type[BaseModel]] | None = None,
    **kwargs,
) -> ReplyMessage: ...


def generate_with_format_by_openai(
    client: OpenAI,
    adapter: ProviderAdapter,
    messages: list[Message],
    response_format: type[BaseModel],
    **kwargs,
) -> ReplyMessage: ...


def generate_with_format_by_anthropic(
    client: Anthropic,
    adapter: ProviderAdapter,
    messages: list[Message],
    response_format: type[BaseModel],
    **kwargs,
) -> ReplyMessage: ...
