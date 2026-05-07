"""模型 API 网关。

统一封装兼容协议的 HTTP 调用，避免把业务代码绑定到单一 SDK。
当前支持两类协议：

- `responses`
- `chat/completions`
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.services.model_api_profiles import (
    ModelApiProfile,
    resolve_model_api_profile,
    resolve_model_api_protocol,
)


class ModelApiFeatureUnavailableError(RuntimeError):
    """当前 provider 或协议不支持请求中的某种输入能力。"""


@dataclass(frozen=True)
class ModelApiConfig:
    """模型 API 访问配置。"""

    provider: str
    api_key: str | None
    base_url: str | None
    timeout_seconds: float
    protocol: str | None = None


class ModelApiGateway:
    """基于纯 HTTP 的兼容网关。"""

    def __init__(self, config: ModelApiConfig) -> None:
        self._profile = resolve_model_api_profile(config.provider)
        self._provider = self._profile.provider
        self._protocol = resolve_model_api_protocol(config.provider, config.protocol)
        self._base_url = (config.base_url or self._profile.default_base_url or "").strip().rstrip("/")
        self._enabled = bool(config.api_key and self._base_url)
        if not self._enabled:
            self._client = None
            return

        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=config.timeout_seconds,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
        )

    @property
    def enabled(self) -> bool:
        return self._enabled and self._client is not None

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def protocol(self) -> str:
        return self._protocol

    @property
    def profile(self) -> ModelApiProfile:
        return self._profile

    @property
    def supports_image_input(self) -> bool:
        return self._profile.supports_image_input

    @property
    def supports_file_input(self) -> bool:
        return self._protocol == "responses" and self._profile.supports_file_input

    def request_text(
        self,
        *,
        model: str,
        instructions: str,
        input_payload: Any,
        max_output_tokens: int,
        reasoning_effort: str | None = None,
        temperature: float | int | None = None,
    ) -> str | None:
        """请求纯文本输出。"""
        if not self._client:
            return None

        if self._protocol == "responses":
            return self._request_via_responses(
                model=model,
                instructions=instructions,
                input_payload=input_payload,
                max_output_tokens=max_output_tokens,
                reasoning_effort=reasoning_effort,
                temperature=temperature,
            )
        if self._protocol == "chat_completions":
            return self._request_via_chat_completions(
                model=model,
                instructions=instructions,
                input_payload=input_payload,
                max_output_tokens=max_output_tokens,
                reasoning_effort=reasoning_effort,
                temperature=temperature,
            )
        raise ValueError(f"Unsupported model api protocol: {self._protocol}")

    def _request_via_responses(
        self,
        *,
        model: str,
        instructions: str,
        input_payload: Any,
        max_output_tokens: int,
        reasoning_effort: str | None,
        temperature: float | int | None,
    ) -> str | None:
        request_body: dict[str, Any] = {
            "model": model,
            "input": self._normalize_responses_input(input_payload),
            "max_output_tokens": max_output_tokens,
        }
        if instructions:
            request_body["instructions"] = instructions
        if temperature is not None:
            request_body["temperature"] = temperature
        if reasoning_effort and self._profile.supports_reasoning_effort:
            request_body["reasoning"] = {"effort": reasoning_effort}

        response = self._post_json_with_parameter_fallback("responses", request_body)
        response.raise_for_status()
        payload = response.json()
        text = str(payload.get("output_text") or "").strip()
        if text:
            return text

        output_items = payload.get("output")
        if not isinstance(output_items, list):
            return None

        fragments: list[str] = []
        for item in output_items:
            if not isinstance(item, dict):
                continue
            for content_part in item.get("content") or []:
                if not isinstance(content_part, dict):
                    continue
                text_value = content_part.get("text") or content_part.get("content")
                if text_value:
                    fragments.append(str(text_value).strip())

        merged_text = "\n".join(fragment for fragment in fragments if fragment).strip()
        return merged_text or None

    def _request_via_chat_completions(
        self,
        *,
        model: str,
        instructions: str,
        input_payload: Any,
        max_output_tokens: int,
        reasoning_effort: str | None,
        temperature: float | int | None,
    ) -> str | None:
        request_body: dict[str, Any] = {
            "model": model,
            "messages": self._build_chat_messages(
                instructions=instructions,
                input_payload=input_payload,
            ),
            "stream": False,
            "max_tokens": max_output_tokens,
        }
        if temperature is not None:
            request_body["temperature"] = temperature
        if reasoning_effort and self._profile.supports_reasoning_effort:
            request_body["reasoning_effort"] = reasoning_effort

        response = self._post_json_with_parameter_fallback("chat/completions", request_body)
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None

        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            return None

        content = message.get("content")
        if isinstance(content, str):
            return content.strip() or None
        if isinstance(content, list):
            fragments: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text_value = item.get("text") or item.get("content")
                if text_value:
                    fragments.append(str(text_value).strip())
            merged_text = "\n".join(fragment for fragment in fragments if fragment).strip()
            return merged_text or None
        return None

    def _normalize_responses_input(self, input_payload: Any) -> Any:
        if isinstance(input_payload, (str, list)):
            return input_payload
        return json.dumps(input_payload, ensure_ascii=False)

    def _post_json_with_parameter_fallback(
        self,
        path: str,
        request_body: dict[str, Any],
    ) -> httpx.Response:
        response = self._client.post(path, json=request_body)
        if (
            response.status_code == 400
            and "temperature" in request_body
            and self._is_unsupported_parameter_error(response, "temperature")
        ):
            retry_body = dict(request_body)
            retry_body.pop("temperature", None)
            return self._client.post(path, json=retry_body)
        return response

    def _is_unsupported_parameter_error(self, response: httpx.Response, parameter: str) -> bool:
        try:
            payload = response.json()
        except ValueError:
            message = response.text
            error_parameter = ""
        else:
            error = payload.get("error") if isinstance(payload, dict) else None
            if not isinstance(error, dict):
                return False
            message = str(error.get("message") or "")
            error_parameter = str(error.get("param") or "")

        normalized_message = message.lower()
        normalized_parameter = parameter.lower()
        return (
            error_parameter.lower() == normalized_parameter
            or (
                "unsupported parameter" in normalized_message
                and normalized_parameter in normalized_message
            )
        )

    def _build_chat_messages(
        self,
        *,
        instructions: str,
        input_payload: Any,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if instructions:
            messages.append({"role": "system", "content": instructions})

        if isinstance(input_payload, str):
            messages.append({"role": "user", "content": input_payload})
            return messages

        if isinstance(input_payload, list):
            for raw_message in input_payload:
                if not isinstance(raw_message, dict):
                    continue
                role = str(raw_message.get("role") or "user").strip() or "user"
                messages.append(
                    {
                        "role": role,
                        "content": self._normalize_chat_content(raw_message.get("content")),
                    }
                )
            return messages

        messages.append({"role": "user", "content": json.dumps(input_payload, ensure_ascii=False)})
        return messages

    def _normalize_chat_content(self, content: Any) -> Any:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return json.dumps(content, ensure_ascii=False)

        normalized_items: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                normalized_items.append({"type": "text", "text": str(item)})
                continue

            item_type = str(item.get("type") or "").strip().lower()
            if item_type in {"input_text", "text"}:
                normalized_items.append({"type": "text", "text": str(item.get("text") or "")})
                continue

            if item_type in {"input_image", "image_url"}:
                if not self.supports_image_input:
                    raise ModelApiFeatureUnavailableError(
                        f"Provider {self._provider} does not support image inputs."
                    )
                image_value = item.get("image_url")
                image_payload = image_value if isinstance(image_value, dict) else {"url": image_value}
                if item.get("detail") and isinstance(image_payload, dict) and "detail" not in image_payload:
                    image_payload["detail"] = item.get("detail")
                normalized_items.append({"type": "image_url", "image_url": image_payload})
                continue

            if item_type in {"input_file", "file", "file_url"}:
                raise ModelApiFeatureUnavailableError(
                    f"Provider {self._provider} with protocol {self._protocol} does not support inline file inputs."
                )

            normalized_items.append({"type": "text", "text": json.dumps(item, ensure_ascii=False)})

        return normalized_items


def build_model_api_gateway(config: ModelApiConfig) -> ModelApiGateway:
    """按 provider 和协议构建模型 API 网关。"""
    return ModelApiGateway(config)
