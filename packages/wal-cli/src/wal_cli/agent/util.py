# packages/wal-cli/src/wal_cli/agent/util.py

from typing import Iterable

from pydantic import BaseModel
from anthropic import Anthropic
from anthropic.types.message_param import MessageParam
from anthropic.types.tool_result_block_param import ToolResultBlockParam
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolUnionParam,
)

from wal_cli.agent.schema import AgentConfig
from wal_cli.agent.schema.message import Message, ReplyMessage, TextContent, ToolCallContent, ToolMessage, Usage
from wal_cli.agent.schema.provider import ProviderInfo


def transform_messages_to_openai(messages: list[Message]) -> Iterable[ChatCompletionMessageParam]:
    data = [message.to_openai() for message in messages]
    return data


def transform_messages_to_anthropic(messages: list[Message]) -> Iterable[MessageParam]:
    data = []
    tools_result = []

    def flush_tool_message():
        if tools_result:
            data.append(MessageParam(role="user", content=tools_result.copy()))
            tools_result.clear()

    for msg in messages:
        if isinstance(msg, ToolMessage):
            tools_result.append(
                ToolResultBlockParam(
                    type="tool_result",
                    tool_use_id=msg.call_id,
                    content=[block.to_anthropic() for block in msg.content],
                    is_error=(not msg.success),
                )
            )
        else:
            flush_tool_message()
            data.append(msg.to_anthropic())

    flush_tool_message()
    return data


def reply_from_openai(response, info: ProviderInfo) -> ReplyMessage:
    choice = response.choices[0]
    message = choice.message

    # Build content list
    content = []

    # Add text content if present
    if message.content:
        content.append(TextContent(text=message.content))

    # Add tool calls if present
    if message.tool_calls:
        for tool_call in message.tool_calls:
            content.append(
                ToolCallContent(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=tool_call.function.arguments,
                )
            )

    # Build usage info.
    #
    # NOTE: response.usage may differ across OpenAI-compatible providers.
    # Some vendors expose non-standard fields or omit nested details.
    # When adding new providers, capture real API responses (curl or
    # OpenAPI spec) and adjust field access patterns here.
    #
    # TODO: guard response.usage with per-provider field mapping.
    usage = Usage(
        input=response.usage.prompt_tokens,
        output=response.usage.completion_tokens,
        context=response.usage.total_tokens,
        cached=getattr(response.usage.prompt_tokens_details, "cached_tokens", 0)
        if response.usage and response.usage.prompt_tokens_details
        else 0,
    )

    return ReplyMessage(
        content=content,
        usage=usage,
        model=f"{info.provider_id}:{info.model_id}",
        refusal=message.refusal,
    )


def reply_from_anthropic(response, info: ProviderInfo) -> ReplyMessage: ...


def generate_by_openai(
    info: ProviderInfo,
    *,
    client: OpenAI,
    messages: list[Message],
    tools: Iterable[ChatCompletionToolUnionParam] | None = None,
    **kwargs,
) -> ReplyMessage:
    msgs = transform_messages_to_openai(messages)
    create_kwargs = {"model": info.model_id, "messages": msgs, **kwargs}
    if tools is not None:
        create_kwargs["tools"] = tools
    response = client.chat.completions.create(**create_kwargs)
    return reply_from_openai(response, info)


def generate_by_anthropic(
    info: ProviderInfo,
    *,
    client: Anthropic,
    messages: list[Message],
    tools: list[type[BaseModel]] | None = None,
    **kwargs,
) -> ReplyMessage: ...


def generate_with_format_by_openai(
    info: ProviderInfo,
    *,
    client: OpenAI,
    messages: list[Message],
    response_format: type[BaseModel],
    **kwargs,
) -> ReplyMessage: ...


def generate_with_format_by_anthropic(
    info: ProviderInfo,
    *,
    client: Anthropic,
    messages: list[Message],
    response_format: type[BaseModel],
    **kwargs,
) -> ReplyMessage: ...


class LLM:
    def __init__(self, identity: str, config: AgentConfig):
        self.identity = identity

        provider_id, model_id = identity.split(":", 1)
        self.config = config
        provider = config.providers[provider_id]
        model = provider.models[model_id]
        self.info = ProviderInfo(
            provider_id=provider_id,
            provider=provider,
            model_id=model_id,
            model=model,
        )

        self.client = self.info.provider.get_client()

    def generate(self, messages: list[Message], **kwargs):
        if isinstance(self.client, OpenAI):
            return generate_by_openai(self.info, client=self.client, messages=messages, **kwargs)
        elif isinstance(self.client, Anthropic):
            return generate_by_anthropic(self.info, client=self.client, messages=messages, **kwargs)

    def generate_with_format(self, messages: list[Message], response_format: type[BaseModel], **kwargs):
        if isinstance(self.client, OpenAI):
            return generate_with_format_by_openai(
                self.info, client=self.client, messages=messages, response_format=response_format, **kwargs
            )
        elif isinstance(self.client, Anthropic):
            return generate_with_format_by_anthropic(
                self.info, client=self.client, messages=messages, response_format=response_format, **kwargs
            )
