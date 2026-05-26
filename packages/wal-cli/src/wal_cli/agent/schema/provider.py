# packages/wal-cli/src/wal_cli/agent/schema/provider.py


from abc import ABC, abstractmethod
from enum import Enum
from typing import Annotated, Literal, Union

from anthropic import Anthropic
from openai import OpenAI
from pydantic import BaseModel, Field


class ModelContextInfo(BaseModel):
    max_tokens: int


class ModelConfig(BaseModel):
    context: ModelContextInfo
    # info_id: str  # openrouter id: <https://openrouter.ai/api/v1/models?output_modalities=all>


class ProviderAdapter(str, Enum):
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC_COMPATIBLE = "anthropic_compatible"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    OPENROUTER = "openrouter"


class ProviderBase(BaseModel, ABC):
    adapter: ProviderAdapter
    base_url: str
    api_key: str
    models: dict[str, ModelConfig]

    @abstractmethod
    def get_client(self): ...


class OpenAICompatibleProvider(ProviderBase):
    adapter: Literal[ProviderAdapter.OPENAI_COMPATIBLE] = ProviderAdapter.OPENAI_COMPATIBLE

    def get_client(self):
        return OpenAI(base_url=self.base_url, api_key=self.api_key)


class AnthropicCompatibleProvider(ProviderBase):
    adapter: Literal[ProviderAdapter.ANTHROPIC_COMPATIBLE] = ProviderAdapter.ANTHROPIC_COMPATIBLE

    def get_client(self):
        return Anthropic(base_url=self.base_url, api_key=self.api_key)


class OpenAIProvider(OpenAICompatibleProvider):
    adapter: Literal[ProviderAdapter.OPENAI] = ProviderAdapter.OPENAI


class AnthropicProvider(AnthropicCompatibleProvider):
    adapter: Literal[ProviderAdapter.ANTHROPIC] = ProviderAdapter.ANTHROPIC


class DeepSeekProvider(OpenAICompatibleProvider):
    adapter: Literal[ProviderAdapter.DEEPSEEK] = ProviderAdapter.DEEPSEEK
    base_url: str = Field(default="https://api.deepseek.com")


class OpenRouterProvider(OpenAICompatibleProvider):
    adapter: Literal[ProviderAdapter.OPENROUTER] = ProviderAdapter.OPENROUTER
    base_url: str = Field(default="https://openrouter.ai/api/v1")


ProviderConfig = Annotated[
    Union[
        OpenAICompatibleProvider,
        AnthropicCompatibleProvider,
        OpenAIProvider,
        AnthropicProvider,
        DeepSeekProvider,
    ],
    Field(discriminator="adapter"),
]


class ProviderInfo(BaseModel):
    provider_id: str
    provider: ProviderConfig
    model_id: str
    model: ModelConfig
