# packages/wal-cli/src/wal_cli/pydantic_agent/util.py

# Provider imports
import hashlib
import importlib.util
from pathlib import Path
from typing import Iterable

from pydantic_ai import ModelMessage
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.groq import GroqProvider
from pydantic_ai.providers.bedrock import BedrockProvider
from pydantic_ai.providers.huggingface import HuggingFaceProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.providers.xai import XaiProvider
from pydantic_ai.providers.cerebras import CerebrasProvider
from pydantic_ai.providers.ollama import OllamaProvider

# Model imports
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.models.bedrock import BedrockConverseModel
from pydantic_ai.models.huggingface import HuggingFaceModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.models.xai import XaiModel
from pydantic_ai.models.cerebras import CerebrasModel

# from pydantic_ai.models.ollama import OllamaModel # Ollama Provides an OpenAI-Compatible Chat Completions API
from pydantic_ai.models.function import _estimate_usage
from pydantic_ai.capabilities import AbstractCapability

# local imports
from wal_cli.config.schema import ProviderType
from wal_cli.config.hub import load_config


def get_model_infrastructure(model_id: str):
    config = load_config()
    provider_name, model_name = model_id.split(":", 1)
    provider_config, model_config = config.get_provider_and_model_config(provider_name, model_name)

    match provider_config.type:
        case ProviderType.ANTHROPIC:
            provider = AnthropicProvider(api_key=provider_config.api_key, base_url=provider_config.base_url)
            infrastructure = AnthropicModel(model_name, provider=provider)

        case ProviderType.BEDROCK:
            if provider_config.api_key is None:
                raise ValueError("Bedrock api_key is required.")
            provider = BedrockProvider(api_key=provider_config.api_key, base_url=provider_config.base_url)
            infrastructure = BedrockConverseModel(model_name, provider=provider)

        case ProviderType.CEREBRAS:
            if provider_config.api_key is None:
                raise ValueError("Cerebras api_key is required.")
            provider = CerebrasProvider(api_key=provider_config.api_key)
            infrastructure = CerebrasModel(model_name, provider=provider)

        case ProviderType.COHERE:
            raise ValueError("Cohere is not supported yet.")
            # provider = CohereProvider(api_key=provider_config.api_key, base_url=provider_config.base_url)
            # infrastructure = CohereModel(model_name, provider=provider)

        case ProviderType.DEEPSEEK:
            provider = OpenAIProvider(api_key=provider_config.api_key, base_url=provider_config.base_url)
            infrastructure = OpenAIChatModel(model_name, provider=provider)

        case ProviderType.GOOGLE:
            provider = GoogleProvider(api_key=provider_config.api_key, base_url=provider_config.base_url)
            infrastructure = GoogleModel(model_name, provider=provider)

        case ProviderType.GROQ:
            provider = GroqProvider(api_key=provider_config.api_key, base_url=provider_config.base_url)
            infrastructure = GroqModel(model_name, provider=provider)

        case ProviderType.HUGGINGFACE:
            if provider_config.base_url is None:
                raise ValueError("HuggingFace requires a base URL.")
            provider = HuggingFaceProvider(api_key=provider_config.api_key, base_url=provider_config.base_url)
            infrastructure = HuggingFaceModel(model_name, provider=provider)

        case ProviderType.MISTRAL:
            raise ValueError("Mistral is not currently supported.")
            # provider = MistralProvider()
            # infrastructure = MistralModel(model_name, provider=provider)

        case ProviderType.OLLAMA:
            provider = OllamaProvider(api_key=provider_config.api_key, base_url=provider_config.base_url)
            infrastructure = OpenAIChatModel(model_name, provider=provider)

        case ProviderType.OPENAI:
            provider = OpenAIProvider(api_key=provider_config.api_key, base_url=provider_config.base_url)
            infrastructure = OpenAIChatModel(model_name, provider=provider)

        case ProviderType.OPENROUTER:
            provider = OpenRouterProvider(api_key=provider_config.api_key)
            infrastructure = OpenRouterModel(model_name, provider=provider)

        case ProviderType.XAI:
            if provider_config.api_key is None:
                raise ValueError("XAI requires an API key.")
            provider = XaiProvider(api_key=provider_config.api_key)
            infrastructure = XaiModel(model_name, provider=provider)

        case _:
            raise ValueError(f"{provider_config.type} is not a valid provider type.")

    return infrastructure, model_config


def estimate_tokens(messages: Iterable[ModelMessage], safety_margin: int = 0) -> int:
    # byte_length = len(text.encode("utf-8"))
    # estimated_tokens = byte_length >> 2
    estimated_tokens = _estimate_usage(messages)
    return estimated_tokens.total_tokens + safety_margin


type CapabilityType = type[AbstractCapability]
type CapabilityList = list[CapabilityType]


def load_custom_capability(paths: Iterable[str]) -> CapabilityList:
    capability_types: CapabilityList = []
    seen: set[CapabilityType] = set()

    for path in filter(str.strip, paths):
        if path.endswith(".py"):
            capability_types.extend(_load_from_file(path, seen))
        elif ":" in path:
            capability_types.extend(_load_from_module_class(path, seen))
        else:
            capability_types.extend(_load_from_module(path, seen))

    return capability_types


def _load_from_file(file_path: str, seen: set[CapabilityType]) -> CapabilityList:
    path = Path(file_path).resolve()
    if not path.exists():
        raise ValueError(f"file {file_path} does not exist")

    path_hash = hashlib.sha256(str(path).encode()).hexdigest()[:8]
    module_name = f"capability_{path.stem}_{path_hash}"

    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None:
        raise ValueError(f"could not load file {file_path}")

    if spec.loader is None:
        raise ValueError(f"no loader found for file {file_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return _collect_from_module(module, seen)


def _load_from_module_class(path: str, seen: set[CapabilityType]) -> CapabilityList:
    try:
        module_path, class_name = path.rsplit(":", 1)
    except ValueError as exc:
        raise ValueError(f"invalid path format {path} expected module colon class") from exc

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(f"could not import module {module_path}") from exc

    if not hasattr(module, class_name):
        raise AttributeError(f"class {class_name} not found in module {module_path}")

    cls = getattr(module, class_name)

    if not (isinstance(cls, type) and issubclass(cls, AbstractCapability)):
        raise TypeError(f"{class_name} is not a subclass of abstract capability")

    if cls not in seen:
        seen.add(cls)
        return [cls]

    return []


def _load_from_module(module_path: str, seen: set[CapabilityType]) -> CapabilityList:
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(f"could not import module {module_path}") from exc

    return _collect_from_module(module, seen)


def _collect_from_module(module: object, seen: set[CapabilityType]) -> CapabilityList:
    capability_types: CapabilityList = []

    for attr_name in dir(module):
        attr = getattr(module, attr_name)

        if isinstance(attr, type) and issubclass(attr, AbstractCapability) and attr is not AbstractCapability:
            if attr not in seen:
                seen.add(attr)
                capability_types.append(attr)

    return capability_types
