"""模型 API provider 预设。

集中维护各 provider 的默认 base URL、默认协议和能力标记，
避免这些规则散落在配置、网关和文档里。
"""

from __future__ import annotations

from dataclasses import dataclass


ModelApiProtocol = str


@dataclass(frozen=True)
class ModelApiProfile:
    """描述一个 provider 的默认接入方式。"""

    provider: str
    label: str
    default_base_url: str | None
    default_protocol: ModelApiProtocol
    supports_image_input: bool = False
    supports_file_input: bool = False
    supports_reasoning_effort: bool = False


_PROFILE_BY_PROVIDER: dict[str, ModelApiProfile] = {
    "openai": ModelApiProfile(
        provider="openai",
        label="OpenAI",
        default_base_url="https://api.openai.com/v1",
        default_protocol="responses",
        supports_image_input=True,
        supports_file_input=True,
        supports_reasoning_effort=True,
    ),
    "dashscope": ModelApiProfile(
        provider="dashscope",
        label="阿里云百炼",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_protocol="responses",
        supports_image_input=True,
        supports_file_input=True,
        supports_reasoning_effort=True,
    ),
    "deepseek": ModelApiProfile(
        provider="deepseek",
        label="DeepSeek",
        default_base_url="https://api.deepseek.com",
        default_protocol="chat_completions",
        supports_image_input=False,
        supports_file_input=False,
        supports_reasoning_effort=True,
    ),
    "zhipu": ModelApiProfile(
        provider="zhipu",
        label="智谱AI",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        default_protocol="chat_completions",
        supports_image_input=True,
        supports_file_input=False,
        supports_reasoning_effort=False,
    ),
    "compatible": ModelApiProfile(
        provider="compatible",
        label="兼容接口",
        default_base_url=None,
        default_protocol="chat_completions",
        supports_image_input=False,
        supports_file_input=False,
        supports_reasoning_effort=False,
    ),
}

_PROVIDER_ALIASES = {
    "openai_compatible": "compatible",
    "custom": "compatible",
    "custom_compatible": "compatible",
}


def normalize_model_api_provider(provider: str | None) -> str:
    """把环境变量中的 provider 标识规范化。"""
    normalized = str(provider or "").strip().lower() or "dashscope"
    return _PROVIDER_ALIASES.get(normalized, normalized)


def resolve_model_api_profile(provider: str | None) -> ModelApiProfile:
    """按 provider 读取预设；未知值退回通用兼容模式。"""
    normalized = normalize_model_api_provider(provider)
    return _PROFILE_BY_PROVIDER.get(normalized, _PROFILE_BY_PROVIDER["compatible"])


def resolve_model_api_protocol(
    provider: str | None,
    requested_protocol: str | None,
) -> ModelApiProtocol:
    """按 provider 和显式配置决定最终协议。"""
    normalized = str(requested_protocol or "").strip().lower()
    if normalized in {"responses", "chat_completions"}:
        return normalized
    return resolve_model_api_profile(provider).default_protocol


def resolve_model_api_provider_label(provider: str | None) -> str:
    """返回 provider 的默认展示名称。"""
    return resolve_model_api_profile(provider).label
