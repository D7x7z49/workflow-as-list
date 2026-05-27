# packages/wal-cli/src/wal_cli/agent/util.py

import json
from typing import Iterable

from pydantic import BaseModel
from anthropic import Anthropic
from anthropic.types.message_param import MessageParam
from anthropic.types.tool_union_param import ToolUnionParam
from anthropic.types.tool_result_block_param import ToolResultBlockParam
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolUnionParam,
)

from wal_cli.agent.constants import ANTHROPIC_DEFAULT_MAX_TOKENS
from wal_cli.agent.schema import AgentConfig
from wal_cli.agent.schema.message import (
    Message,
    ReplyMessage,
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolMessage,
    Usage,
)
from wal_cli.agent.schema.provider import ProviderInfo


def transform_messages_to_openai(messages: list[Message], info: ProviderInfo) -> Iterable[ChatCompletionMessageParam]:
    data = [message.to_openai(info) for message in messages]
    return data


def transform_messages_to_anthropic(messages: list[Message], info: ProviderInfo) -> Iterable[MessageParam]:
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
            data.append(msg.to_anthropic(info))

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

    if getattr(message, "reasoning_content", None):
        content.append(ThinkingContent(thinking=message.reasoning_content))

    # Build usage info.
    #
    # NOTE: response.usage may differ across OpenAI-compatible providers.
    # Some vendors expose non-standard fields or omit nested details.
    # When adding new providers, capture real API responses (curl or
    # OpenAPI spec) and adjust field access patterns here.
    #
    # TODO: guard response.usage with per-provider field mapping.
    prompt_tokens_details = response.usage.prompt_tokens_details
    cached_tokens = (prompt_tokens_details.cached_tokens or 0) if prompt_tokens_details else 0
    usage = Usage(
        input=response.usage.prompt_tokens,
        output=response.usage.completion_tokens,
        context=response.usage.total_tokens,
        cached=cached_tokens,
    )

    return ReplyMessage(
        content=content,
        usage=usage,
        provider=info.provider_id,
        model=info.model_id,
        refusal=message.refusal,
    )


def reply_from_anthropic(response, info: ProviderInfo) -> ReplyMessage:
    # Build content list from response content blocks
    content = []
    for block in response.content:
        if block.type == "text":
            content.append(TextContent(text=block.text))
        elif block.type == "tool_use":
            content.append(
                ToolCallContent(
                    id=block.id,
                    name=block.name,
                    arguments=json.dumps(block.input) if block.input else "",
                )
            )
        elif block.type == "thinking":
            content.append(ThinkingContent(thinking=block.thinking, thinkingSignature=block.signature))
        elif block.type == "redacted_thinking":
            content.append(ThinkingContent(thinking="", thinkingSignature=block.data, redacted=True))

    # Build usage info.
    #
    # NOTE: cache_read_input_tokens and cache_creation_input_tokens are
    # Optional[int] defaulting to None when no cache is hit. The `or 0`
    # fallback keeps the math safe but may silently mask an unexpected None
    # that should have been a real integer. If cache stats matter for
    # billing or debugging, consider surfacing None explicitly.
    cache_read_input_tokens = response.usage.cache_read_input_tokens or 0
    cache_creation_input_tokens = response.usage.cache_creation_input_tokens or 0
    usage = Usage(
        input=response.usage.input_tokens,
        output=response.usage.output_tokens,
        context=response.usage.input_tokens + response.usage.output_tokens,
        cached=cache_read_input_tokens + cache_creation_input_tokens,
    )

    return ReplyMessage(
        content=content,
        usage=usage,
        provider=info.provider_id,
        model=info.model_id,
        refusal=None,  # Anthropic doesn't have a direct refusal field like OpenAI
    )


def generate_by_openai(
    info: ProviderInfo,
    *,
    client: OpenAI,
    messages: list[Message],
    tools: Iterable[ChatCompletionToolUnionParam] | None = None,
    **kwargs,
) -> ReplyMessage:
    msgs = transform_messages_to_openai(messages, info)
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
    tools: Iterable[ToolUnionParam] | None = None,
    **kwargs,
) -> ReplyMessage:
    msgs = transform_messages_to_anthropic(messages, info)
    create_kwargs = {"model": info.model_id, "messages": msgs, **kwargs}
    create_kwargs.setdefault("max_tokens", ANTHROPIC_DEFAULT_MAX_TOKENS)
    if tools is not None:
        create_kwargs["tools"] = tools
    response = client.messages.create(**create_kwargs)
    return reply_from_anthropic(response, info)


def generate_with_format_by_openai(
    info: ProviderInfo,
    *,
    client: OpenAI,
    messages: list[Message],
    response_format: type[BaseModel],
    **kwargs,
) -> tuple[ReplyMessage, BaseModel | None]:
    msgs = transform_messages_to_openai(messages, info)
    create_kwargs = {"model": info.model_id, "messages": msgs, **kwargs}

    # parse() wraps create() with response_format -> JSON schema conversion
    # and post-parses message.content into message.parsed (Pydantic model).
    # ParsedChatCompletion extends ChatCompletion, so reply_from_openai handles
    # content extraction identically to the non-format path.
    response = client.chat.completions.parse(
        **create_kwargs,
        response_format=response_format,
    )
    parsed = response.choices[0].message.parsed
    return reply_from_openai(response, info), parsed


def generate_with_format_by_anthropic(
    info: ProviderInfo,
    *,
    client: Anthropic,
    messages: list[Message],
    response_format: type[BaseModel],
    **kwargs,
) -> tuple[ReplyMessage, BaseModel | None]:
    msgs = transform_messages_to_anthropic(messages, info)
    create_kwargs = {"model": info.model_id, "messages": msgs, **kwargs}
    create_kwargs.setdefault("max_tokens", ANTHROPIC_DEFAULT_MAX_TOKENS)

    # parse() wraps create() with output_format → JSON schema conversion
    # and returns ParsedMessage which contains both the raw message and parsed model
    response = client.messages.parse(
        **create_kwargs,
        output_format=response_format,
    )

    parsed = response.parsed_output
    return reply_from_anthropic(response, info), parsed


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

    def generate(self, messages: list[Message], **kwargs) -> ReplyMessage:
        if isinstance(self.client, OpenAI):
            return generate_by_openai(self.info, client=self.client, messages=messages, **kwargs)
        elif isinstance(self.client, Anthropic):
            return generate_by_anthropic(self.info, client=self.client, messages=messages, **kwargs)
        raise ValueError(f"unsupported client type: {type(self.client)}")

    def generate_with_format(self, messages: list[Message], response_format: type[BaseModel], **kwargs):
        if isinstance(self.client, OpenAI):
            return generate_with_format_by_openai(
                self.info, client=self.client, messages=messages, response_format=response_format, **kwargs
            )
        elif isinstance(self.client, Anthropic):
            return generate_with_format_by_anthropic(
                self.info, client=self.client, messages=messages, response_format=response_format, **kwargs
            )
