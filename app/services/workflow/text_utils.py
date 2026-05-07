"""文本清洗与合并工具。"""

from __future__ import annotations

import re


def normalize_text_for_compare(value: str) -> str:
    """把文本标准化，便于做去重和包含判断。"""
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def merge_text_sources(
    primary_text: str,
    secondary_text: str,
    *,
    separator_label: str | None = "补全文本",
) -> str:
    """合并正文和 OCR 文本，尽量避免重复内容。"""
    primary = str(primary_text or "").strip()
    secondary = str(secondary_text or "").strip()

    if not primary:
        return secondary
    if not secondary:
        return primary

    normalized_primary = normalize_text_for_compare(primary)
    normalized_secondary = normalize_text_for_compare(secondary)

    if normalized_primary == normalized_secondary:
        return primary if len(primary) >= len(secondary) else secondary
    if normalized_secondary and normalized_secondary in normalized_primary:
        return primary
    if normalized_primary and normalized_primary in normalized_secondary:
        return secondary

    primary_lines = [line.strip() for line in primary.splitlines() if line.strip()]
    seen_lines = {normalize_text_for_compare(line) for line in primary_lines}
    extra_lines = [
        line.strip()
        for line in secondary.splitlines()
        if line.strip() and normalize_text_for_compare(line) not in seen_lines
    ]
    if not extra_lines:
        return primary if len(primary) >= len(secondary) else secondary

    merged_extra = "\n".join(extra_lines).strip()
    if not separator_label:
        return f"{primary.rstrip()}\n{merged_extra}".strip()

    return f"{primary.rstrip()}\n\n[{separator_label}]\n{merged_extra}".strip()
