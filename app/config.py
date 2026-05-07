"""应用配置读取。

负责从环境变量加载模型 API、OCR、存储和上传解析相关配置，并统一提供给全局使用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from app.services.model_api_profiles import (
    normalize_model_api_provider,
    resolve_model_api_profile,
    resolve_model_api_protocol,
    resolve_model_api_provider_label,
)


load_dotenv()


@dataclass(frozen=True)
class Settings:
    """应用运行期配置对象。"""

    model_api_provider: str
    model_api_provider_label: str
    model_api_protocol: str
    model_api_key: str | None
    model_api_base_url: str | None
    model_api_model: str
    model_api_timeout_seconds: float
    model_api_reasoning_effort: str
    model_api_heavy_reasoning_effort: str
    model_api_agent_enabled: bool
    model_api_ocr_provider: str
    model_api_ocr_provider_label: str
    model_api_ocr_protocol: str
    model_api_ocr_key: str | None
    model_api_ocr_base_url: str | None
    model_api_ocr_enabled: bool
    model_api_ocr_model: str
    model_api_ocr_timeout_seconds: float
    model_api_ocr_max_output_tokens: int
    model_api_ocr_image_detail: str
    model_api_ocr_pdf_mode: str
    model_api_ocr_pdf_pages_per_request: int
    model_api_review_provider: str
    model_api_review_provider_label: str
    model_api_review_protocol: str
    model_api_review_key: str | None
    model_api_review_base_url: str | None
    model_api_review_enabled: bool
    model_api_review_model: str
    model_api_review_timeout_seconds: float
    model_api_review_max_output_tokens: int
    model_api_review_block_on_high_risk: bool
    database_url: str
    workflow_storage_dir: str
    workflow_worker_count: int
    workflow_job_heartbeat_timeout_seconds: int
    workflow_zip_entry_limit: int
    workflow_zip_total_size_limit_bytes: int
    upload_text_char_limit: int | None
    upload_table_row_limit: int | None
    upload_table_column_limit: int | None
    upload_pdf_page_limit: int | None


def _env_bool(name: str, default: bool) -> bool:
    """把环境变量解析为布尔值。"""
    raw_value = os.getenv(name, str(default)).strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _env_float(name: str, default: float) -> float:
    """把环境变量解析为浮点数。"""
    raw_value = os.getenv(name, str(default)).strip() or str(default)
    return float(raw_value)


def _env_int(name: str, default: int) -> int:
    """把环境变量解析为整数。"""
    raw_value = os.getenv(name, str(default)).strip() or str(default)
    return int(raw_value)


def _env_optional_str(name: str, default: str | None = None) -> str | None:
    """把环境变量解析为可选字符串。"""
    fallback = default or ""
    value = os.getenv(name, fallback).strip()
    return value or None


def _env_choice(name: str, default: str, choices: set[str]) -> str:
    """把环境变量限制在给定候选值内。"""
    value = (os.getenv(name, default).strip().lower() or default).lower()
    return value if value in choices else default


def _env_optional_positive_int(name: str, default: int | None) -> int | None:
    """把环境变量解析为可选正整数，空值或 0 视为未设置。"""
    fallback = "" if default is None else str(default)
    raw_value = os.getenv(name, fallback).strip()
    if not raw_value or raw_value == "0":
        return None

    parsed_value = int(raw_value)
    return parsed_value if parsed_value > 0 else None


def _infer_model_api_provider() -> str:
    """根据显式 provider 或环境变量命名推断默认模型 provider。"""
    explicit_provider = _env_optional_str("MODEL_API_PROVIDER")
    if explicit_provider:
        return normalize_model_api_provider(explicit_provider)

    legacy_provider = _env_optional_str("OPENAI_PROVIDER")
    if legacy_provider:
        return normalize_model_api_provider(legacy_provider)

    openai_env_present = any(
        _env_optional_str(name)
        for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")
    )
    return "openai" if openai_env_present else "dashscope"


def _infer_model_api_review_provider() -> str:
    """根据 review 专用配置推断交叉检查 agent 的 provider。"""
    explicit_provider = _env_optional_str("MODEL_API_REVIEW_PROVIDER")
    if explicit_provider:
        return normalize_model_api_provider(explicit_provider)

    openai_review_provider = _env_optional_str("OPENAI_REVIEW_PROVIDER")
    if openai_review_provider:
        return normalize_model_api_provider(openai_review_provider)

    openai_review_env_present = any(
        _env_optional_str(name)
        for name in (
            "OPENAI_REVIEW_API_KEY",
            "OPENAI_REVIEW_KEY",
            "OPENAI_REVIEW_BASE_URL",
            "OPENAI_REVIEW_MODEL",
        )
    )
    return "openai" if openai_review_env_present else "deepseek"


def _default_review_model(
    *,
    review_provider: str,
    main_provider: str,
    main_model: str,
) -> str:
    """返回 review agent 的保守默认模型。"""
    if review_provider == main_provider:
        return main_model
    if review_provider == "deepseek":
        return "deepseek-chat"
    if review_provider == "openai":
        return "gpt-5.4-mini"
    return main_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """构建并缓存全局配置。"""
    default_storage_dir = Path(os.getenv("WORKFLOW_STORAGE_DIR", ".workflow_storage")).expanduser()
    default_database_path = default_storage_dir / "workflow.db"
    database_url = os.getenv(
        "DATABASE_URL",
        f"sqlite+pysqlite:///{default_database_path}",
    ).strip() or f"sqlite+pysqlite:///{default_database_path}"

    model_api_provider = _infer_model_api_provider()
    model_api_protocol = resolve_model_api_protocol(
        model_api_provider,
        _env_optional_str("MODEL_API_PROTOCOL") or _env_optional_str("OPENAI_PROTOCOL"),
    )
    model_api_provider_label = (
        _env_optional_str("MODEL_API_PROVIDER_LABEL")
        or resolve_model_api_provider_label(model_api_provider)
    )
    model_api_key = _env_optional_str("MODEL_API_KEY") or _env_optional_str("OPENAI_API_KEY")
    model_api_base_url = (
        _env_optional_str("MODEL_API_BASE_URL")
        or _env_optional_str("OPENAI_BASE_URL")
        or resolve_model_api_profile(model_api_provider).default_base_url
    )
    model_api_model = os.getenv("MODEL_API_MODEL", os.getenv("OPENAI_MODEL", "qwen-plus")).strip() or "qwen-plus"
    model_api_timeout_seconds = _env_float(
        "MODEL_API_TIMEOUT_SECONDS",
        _env_float("OPENAI_TIMEOUT_SECONDS", 90),
    )
    model_api_reasoning_effort = _env_choice(
        "MODEL_API_REASONING_EFFORT",
        _env_choice(
            "OPENAI_REASONING_EFFORT",
            "medium",
            {"none", "low", "medium", "high", "xhigh"},
        ),
        {"none", "low", "medium", "high", "xhigh"},
    )
    model_api_heavy_reasoning_effort = _env_choice(
        "MODEL_API_HEAVY_REASONING_EFFORT",
        _env_choice(
            "OPENAI_HEAVY_REASONING_EFFORT",
            "high",
            {"none", "low", "medium", "high", "xhigh"},
        ),
        {"none", "low", "medium", "high", "xhigh"},
    )
    model_api_agent_enabled = _env_bool(
        "MODEL_API_AGENT_ENABLED",
        _env_bool("OPENAI_AGENT_ENABLED", True),
    )

    model_api_ocr_provider = normalize_model_api_provider(
        _env_optional_str("MODEL_API_OCR_PROVIDER") or model_api_provider
    )
    model_api_ocr_protocol = resolve_model_api_protocol(
        model_api_ocr_provider,
        _env_optional_str("MODEL_API_OCR_PROTOCOL"),
    )
    model_api_ocr_provider_label = (
        _env_optional_str("MODEL_API_OCR_PROVIDER_LABEL")
        or resolve_model_api_provider_label(model_api_ocr_provider)
    )
    model_api_ocr_key = _env_optional_str("MODEL_API_OCR_KEY") or model_api_key
    model_api_ocr_base_url = (
        _env_optional_str("MODEL_API_OCR_BASE_URL")
        or (
            model_api_base_url
            if model_api_ocr_provider == model_api_provider
            else resolve_model_api_profile(model_api_ocr_provider).default_base_url
        )
    )
    model_api_ocr_enabled = _env_bool(
        "MODEL_API_OCR_ENABLED",
        _env_bool("OPENAI_OCR_ENABLED", True),
    )
    model_api_ocr_model = (
        _env_optional_str("MODEL_API_OCR_MODEL")
        or _env_optional_str("OPENAI_OCR_MODEL")
        or model_api_model
    )
    model_api_ocr_timeout_seconds = _env_float(
        "MODEL_API_OCR_TIMEOUT_SECONDS",
        _env_float("OPENAI_OCR_TIMEOUT_SECONDS", 180),
    )
    model_api_ocr_max_output_tokens = _env_int(
        "MODEL_API_OCR_MAX_OUTPUT_TOKENS",
        _env_int("OPENAI_OCR_MAX_OUTPUT_TOKENS", 4000),
    )

    image_detail = (
        os.getenv("MODEL_API_OCR_IMAGE_DETAIL", os.getenv("OPENAI_OCR_IMAGE_DETAIL", "high"))
        .strip()
        .lower()
        or "high"
    )
    pdf_mode = (
        os.getenv("MODEL_API_OCR_PDF_MODE", os.getenv("OPENAI_OCR_PDF_MODE", "hybrid"))
        .strip()
        .lower()
        or "hybrid"
    )
    if image_detail not in {"auto", "low", "high"}:
        image_detail = "high"
    if pdf_mode not in {"off", "fallback", "hybrid"}:
        pdf_mode = "hybrid"

    model_api_ocr_pdf_pages_per_request = _env_int(
        "MODEL_API_OCR_PDF_PAGES_PER_REQUEST",
        _env_int("OPENAI_OCR_PDF_PAGES_PER_REQUEST", 1),
    )

    model_api_review_provider = _infer_model_api_review_provider()
    model_api_review_protocol = resolve_model_api_protocol(
        model_api_review_provider,
        _env_optional_str("MODEL_API_REVIEW_PROTOCOL") or _env_optional_str("OPENAI_REVIEW_PROTOCOL"),
    )
    model_api_review_provider_label = (
        _env_optional_str("MODEL_API_REVIEW_PROVIDER_LABEL")
        or _env_optional_str("OPENAI_REVIEW_PROVIDER_LABEL")
        or resolve_model_api_provider_label(model_api_review_provider)
    )
    model_api_review_key = (
        _env_optional_str("MODEL_API_REVIEW_KEY")
        or _env_optional_str("OPENAI_REVIEW_API_KEY")
        or _env_optional_str("OPENAI_REVIEW_KEY")
    )
    model_api_review_base_url = (
        _env_optional_str("MODEL_API_REVIEW_BASE_URL")
        or _env_optional_str("OPENAI_REVIEW_BASE_URL")
        or resolve_model_api_profile(model_api_review_provider).default_base_url
    )
    model_api_review_enabled = _env_bool(
        "MODEL_API_REVIEW_ENABLED",
        _env_bool("OPENAI_REVIEW_ENABLED", True),
    )
    model_api_review_model = (
        _env_optional_str("MODEL_API_REVIEW_MODEL")
        or _env_optional_str("OPENAI_REVIEW_MODEL")
        or _default_review_model(
            review_provider=model_api_review_provider,
            main_provider=model_api_provider,
            main_model=model_api_model,
        )
    )
    model_api_review_timeout_seconds = _env_float(
        "MODEL_API_REVIEW_TIMEOUT_SECONDS",
        _env_float("OPENAI_REVIEW_TIMEOUT_SECONDS", 60),
    )
    model_api_review_max_output_tokens = _env_int(
        "MODEL_API_REVIEW_MAX_OUTPUT_TOKENS",
        _env_int("OPENAI_REVIEW_MAX_OUTPUT_TOKENS", 1200),
    )
    model_api_review_block_on_high_risk = _env_bool(
        "MODEL_API_REVIEW_BLOCK_ON_HIGH_RISK",
        _env_bool("OPENAI_REVIEW_BLOCK_ON_HIGH_RISK", True),
    )

    return Settings(
        model_api_provider=model_api_provider,
        model_api_provider_label=model_api_provider_label,
        model_api_protocol=model_api_protocol,
        model_api_key=model_api_key,
        model_api_base_url=model_api_base_url,
        model_api_model=model_api_model,
        model_api_timeout_seconds=model_api_timeout_seconds,
        model_api_reasoning_effort=model_api_reasoning_effort,
        model_api_heavy_reasoning_effort=model_api_heavy_reasoning_effort,
        model_api_agent_enabled=model_api_agent_enabled,
        model_api_ocr_provider=model_api_ocr_provider,
        model_api_ocr_provider_label=model_api_ocr_provider_label,
        model_api_ocr_protocol=model_api_ocr_protocol,
        model_api_ocr_key=model_api_ocr_key,
        model_api_ocr_base_url=model_api_ocr_base_url,
        model_api_ocr_enabled=model_api_ocr_enabled,
        model_api_ocr_model=model_api_ocr_model,
        model_api_ocr_timeout_seconds=model_api_ocr_timeout_seconds,
        model_api_ocr_max_output_tokens=model_api_ocr_max_output_tokens,
        model_api_ocr_image_detail=image_detail,
        model_api_ocr_pdf_mode=pdf_mode,
        model_api_ocr_pdf_pages_per_request=model_api_ocr_pdf_pages_per_request,
        model_api_review_provider=model_api_review_provider,
        model_api_review_provider_label=model_api_review_provider_label,
        model_api_review_protocol=model_api_review_protocol,
        model_api_review_key=model_api_review_key,
        model_api_review_base_url=model_api_review_base_url,
        model_api_review_enabled=model_api_review_enabled,
        model_api_review_model=model_api_review_model,
        model_api_review_timeout_seconds=model_api_review_timeout_seconds,
        model_api_review_max_output_tokens=model_api_review_max_output_tokens,
        model_api_review_block_on_high_risk=model_api_review_block_on_high_risk,
        database_url=database_url,
        workflow_storage_dir=str(default_storage_dir),
        workflow_worker_count=max(1, _env_int("WORKFLOW_WORKER_COUNT", 2)),
        workflow_job_heartbeat_timeout_seconds=max(
            30,
            _env_int("WORKFLOW_JOB_HEARTBEAT_TIMEOUT_SECONDS", 300),
        ),
        workflow_zip_entry_limit=max(1, _env_int("WORKFLOW_ZIP_ENTRY_LIMIT", 50)),
        workflow_zip_total_size_limit_bytes=max(
            1,
            _env_int("WORKFLOW_ZIP_TOTAL_SIZE_LIMIT_BYTES", 100 * 1024 * 1024),
        ),
        upload_text_char_limit=_env_optional_positive_int("WORKFLOW_UPLOAD_TEXT_CHAR_LIMIT", None),
        upload_table_row_limit=_env_optional_positive_int("WORKFLOW_UPLOAD_TABLE_ROW_LIMIT", None),
        upload_table_column_limit=_env_optional_positive_int("WORKFLOW_UPLOAD_TABLE_COLUMN_LIMIT", None),
        upload_pdf_page_limit=_env_optional_positive_int("WORKFLOW_UPLOAD_PDF_PAGE_LIMIT", None),
    )


settings = get_settings()
