# packages/wal-runtime/src/wal_runtime/config/schema.py

from os import environ
from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator

from wal_runtime.config.util import get_pass, parse_suffixed_number


class WhiteList(BaseModel):
    domain: list[str]
    command: list[str]


class ModelConfig(BaseModel):
    context_length: int = Field(..., description="The context length for the model")

    @field_validator("context_length", mode="before", json_schema_input_type=Union[int, str])
    @classmethod
    def parse_context_length(cls, v):
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            return parse_suffixed_number(v)

        raise ValueError(f"Invalid context length: {v}")


class ProviderType(str, Enum):
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    CEREBRAS = "cerebras"
    COHERE = "cohere"
    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    GROQ = "groq"
    HUGGINGFACE = "huggingface"
    MISTRAL = "mistral"
    OLLAMA = "ollama"
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    XAI = "xai"


class ProviderConfig(BaseModel):
    type: ProviderType
    models: dict[str, ModelConfig] = Field(..., description="The models supported by the provider")

    api_key: Optional[str] = Field(None, description="The API key for the provider")
    base_url: Optional[str] = Field(None, description="The base URL for the provider")

    @field_validator("api_key", mode="before")
    @classmethod
    def resolve_api_key(cls, v):
        if isinstance(v, str):
            if v.startswith("env:"):
                v = environ.get(v[4:], "")
            if v.startswith("pass:"):
                entry = v[5:]
                v = get_pass(entry)
        return v


class RuntimeConfig(BaseModel):
    white_list: WhiteList
    providers: dict[str, ProviderConfig] = Field(..., description="The providers supported by the agent")

    def get_provider_and_model_config(self, provider_name: str, model_name: str):
        provider = self.providers[provider_name]
        model = provider.models[model_name]
        return provider, model

    def validate_model_id(self, model_id: str):
        if ":" not in model_id:
            return False, f"{model_id} is not a valid model id, model id format like `provider:model` is required."

        provider_name, model_name = model_id.split(":", 1)

        if provider_name not in self.providers:
            return False, f"Provider {provider_name} not found, available providers are {self.providers.keys()}."

        if model_name not in self.providers[provider_name].models:
            return (
                False,
                f"Model {model_name} not found, available models are {self.providers[provider_name].models.keys()}.",
            )

        return True, (provider_name, model_name)
