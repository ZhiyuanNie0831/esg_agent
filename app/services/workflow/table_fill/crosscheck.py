"""Agent 交叉检查 Excel 写入计划。

交叉检查只判断风险，不直接写 workbook；真正写入仍由本地确定性代码执行。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.services.model_api import ModelApiConfig, build_model_api_gateway

logger = logging.getLogger(__name__)


class TableDataTransferCrossCheckService:
    """用单独的 review 模型 API 检查源表到目标表的写入计划。"""

    def __init__(self) -> None:
        self._client = build_model_api_gateway(
            ModelApiConfig(
                provider=settings.model_api_review_provider,
                api_key=settings.model_api_review_key,
                base_url=settings.model_api_review_base_url,
                timeout_seconds=settings.model_api_review_timeout_seconds,
                protocol=settings.model_api_review_protocol,
            )
        )

    @property
    def enabled(self) -> bool:
        return settings.model_api_review_enabled and self._client.enabled

    def review_transfer_plan(
        self,
        *,
        task: str,
        source_summary: dict[str, Any],
        target_summary: dict[str, Any],
        column_mappings: list[dict[str, object]],
        row_count: int,
    ) -> dict[str, object]:
        """返回交叉检查结果；API 不可用或失败时返回可审计的跳过结果。"""
        base_result = {
            "enabled": self.enabled,
            "provider": settings.model_api_review_provider,
            "providerLabel": settings.model_api_review_provider_label,
            "model": settings.model_api_review_model,
            "status": "skipped",
            "approved": True,
            "riskLevel": "unknown",
            "blockWrite": False,
            "issues": [],
            "suggestions": [],
        }
        if not self.enabled:
            return {
                **base_result,
                "reason": "MODEL_API_REVIEW_KEY/OPENAI_REVIEW_API_KEY 未配置或 review agent 被禁用，已跳过 agent 交叉检查。",
            }

        payload = {
            "task": task,
            "source": source_summary,
            "target": target_summary,
            "columnMappings": column_mappings,
            "rowCount": row_count,
        }
        instructions = (
            "你是 Excel 自动写入计划的审查 agent。"
            "请检查源表、目标表、列映射和写入计划是否合理。"
            "只返回 JSON，不要输出额外说明。"
            "如果源表和目标表可能识别反了、列映射语义不一致、目标列缺失、可能覆盖重要数据，必须标为 high 风险。"
            "JSON 结构必须是："
            '{"approved": true, "riskLevel": "low|medium|high", "issues": [], "suggestions": []}'
        )
        try:
            raw_text = self._client.request_text(
                model=settings.model_api_review_model,
                instructions=instructions,
                input_payload=json.dumps(payload, ensure_ascii=False),
                max_output_tokens=settings.model_api_review_max_output_tokens,
                reasoning_effort=settings.model_api_reasoning_effort,
                temperature=0,
            )
        except Exception:
            logger.exception(
                "table data transfer review request failed: provider=%s model=%s",
                settings.model_api_review_provider,
                settings.model_api_review_model,
            )
            return {
                **base_result,
                "enabled": True,
                "status": "error",
                "approved": not settings.model_api_review_block_on_high_risk,
                "blockWrite": settings.model_api_review_block_on_high_risk,
                "riskLevel": "unknown",
                "reason": "review API 调用失败。",
            }

        parsed = self._parse_json_result(raw_text)
        if parsed is None:
            return {
                **base_result,
                "enabled": True,
                "status": "invalid_response",
                "approved": not settings.model_api_review_block_on_high_risk,
                "blockWrite": settings.model_api_review_block_on_high_risk,
                "riskLevel": "unknown",
                "reason": "review API 未返回合法 JSON。",
            }

        risk_level = self._normalize_risk_level(parsed.get("riskLevel"))
        approved = bool(parsed.get("approved", risk_level != "high"))
        block_write = bool(settings.model_api_review_block_on_high_risk and (risk_level == "high" or not approved))
        return {
            **base_result,
            "enabled": True,
            "status": "completed",
            "approved": approved and not block_write,
            "riskLevel": risk_level,
            "blockWrite": block_write,
            "issues": self._normalize_string_list(parsed.get("issues")),
            "suggestions": self._normalize_string_list(parsed.get("suggestions")),
        }

    def _parse_json_result(self, raw_text: str | None) -> dict[str, Any] | None:
        if not raw_text:
            return None
        stripped = raw_text.strip()
        if stripped.startswith("```"):
            lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
            stripped = "\n".join(lines).strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            return None
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _normalize_risk_level(self, value: object) -> str:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in {"low", "medium", "high"} else "medium"

    def _normalize_string_list(self, values: object) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for value in values:
            item = str(value or "").strip()
            if item and item not in normalized:
                normalized.append(item)
        return normalized[:6]


class TableFillMappingCrossCheckService:
    """用 review 模型 API 检查自动填表候选位置。"""

    def __init__(self) -> None:
        self._client = build_model_api_gateway(
            ModelApiConfig(
                provider=settings.model_api_review_provider,
                api_key=settings.model_api_review_key,
                base_url=settings.model_api_review_base_url,
                timeout_seconds=settings.model_api_review_timeout_seconds,
                protocol=settings.model_api_review_protocol,
            )
        )

    @property
    def enabled(self) -> bool:
        return settings.model_api_review_enabled and self._client.enabled

    def review_mapping_plan(
        self,
        *,
        task: str,
        target_summary: dict[str, Any],
        mapping_candidates: list[dict[str, object]],
    ) -> dict[str, object]:
        """审查候选填位，返回整体风险和可选的逐项风险说明。"""
        base_result = {
            "enabled": self.enabled,
            "provider": settings.model_api_review_provider,
            "providerLabel": settings.model_api_review_provider_label,
            "model": settings.model_api_review_model,
            "status": "skipped",
            "approved": True,
            "riskLevel": "unknown",
            "blockWrite": False,
            "issues": [],
            "suggestions": [],
            "candidateReviews": [],
        }
        if not self.enabled:
            return {
                **base_result,
                "reason": "MODEL_API_REVIEW_KEY/OPENAI_REVIEW_API_KEY 未配置或 review agent 被禁用，已跳过填位交叉检查。",
            }

        payload = {
            "task": task,
            "target": target_summary,
            "candidateCount": len(mapping_candidates),
            "mappingCandidates": [
                self._compact_mapping_candidate(item)
                for item in mapping_candidates
                if isinstance(item, dict)
            ],
        }
        instructions = (
            "你是 Excel 自动填表位置审查 agent。"
            "请检查每条候选填位是否符合用户任务、指标语义、来源字段、目标 sheet/cell 和模板上下文。"
            "只返回 JSON，不要输出额外说明。"
            "如果目标 sheet 可能选错、指标与标签语义不一致、候选 cell 缺失/明显偏移、可能覆盖重要数据，必须标为 high 风险。"
            "candidateReviews 只需要列出有风险或需要调整的候选，不要逐条复述全部低风险候选。"
            "JSON 结构必须是："
            '{"approved": true, "riskLevel": "low|medium|high", "issues": [], "suggestions": [], '
            '"candidateReviews": [{"mappingId": "map_1", "approved": true, "riskLevel": "low|medium|high", '
            '"issue": "", "suggestedSheet": "", "suggestedCell": ""}]}'
        )
        try:
            raw_text = self._client.request_text(
                model=settings.model_api_review_model,
                instructions=instructions,
                input_payload=json.dumps(payload, ensure_ascii=False),
                max_output_tokens=settings.model_api_review_max_output_tokens,
                reasoning_effort=settings.model_api_reasoning_effort,
                temperature=0,
            )
        except Exception:
            logger.exception(
                "table fill mapping review request failed: provider=%s model=%s",
                settings.model_api_review_provider,
                settings.model_api_review_model,
            )
            return {
                **base_result,
                "enabled": True,
                "status": "error",
                "approved": not settings.model_api_review_block_on_high_risk,
                "blockWrite": settings.model_api_review_block_on_high_risk,
                "riskLevel": "unknown",
                "reason": "review API 调用失败。",
            }

        parsed = self._parse_json_result(raw_text)
        if parsed is None:
            return {
                **base_result,
                "enabled": True,
                "status": "invalid_response",
                "approved": not settings.model_api_review_block_on_high_risk,
                "blockWrite": settings.model_api_review_block_on_high_risk,
                "riskLevel": "unknown",
                "reason": "review API 未返回合法 JSON。",
            }

        risk_level = self._normalize_risk_level(parsed.get("riskLevel"))
        approved = bool(parsed.get("approved", risk_level != "high"))
        block_write = bool(settings.model_api_review_block_on_high_risk and (risk_level == "high" or not approved))
        return {
            **base_result,
            "enabled": True,
            "status": "completed",
            "approved": approved and not block_write,
            "riskLevel": risk_level,
            "blockWrite": block_write,
            "issues": self._normalize_string_list(parsed.get("issues")),
            "suggestions": self._normalize_string_list(parsed.get("suggestions")),
            "candidateReviews": self._normalize_candidate_reviews(parsed.get("candidateReviews")),
        }

    def _compact_mapping_candidate(self, item: dict[str, object]) -> dict[str, object]:
        return {
            "mappingId": item.get("mappingId"),
            "metric": item.get("metric"),
            "sourceDocument": item.get("sourceDocument"),
            "sourceSheet": item.get("sourceSheet"),
            "sourceColumn": item.get("sourceColumn"),
            "value": item.get("value"),
            "targetSheet": item.get("sheet"),
            "targetCell": item.get("cell"),
            "status": item.get("status"),
            "mode": item.get("mode"),
            "confidence": item.get("confidence"),
            "score": item.get("score"),
            "riskLevel": item.get("riskLevel"),
            "reasons": list(item.get("reasons", []) or [])[:3],
        }

    def _parse_json_result(self, raw_text: str | None) -> dict[str, Any] | None:
        if not raw_text:
            return None
        stripped = raw_text.strip()
        if stripped.startswith("```"):
            lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
            stripped = "\n".join(lines).strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            return None
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _normalize_risk_level(self, value: object) -> str:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in {"low", "medium", "high"} else "medium"

    def _normalize_string_list(self, values: object) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for value in values:
            item = str(value or "").strip()
            if item and item not in normalized:
                normalized.append(item)
        return normalized[:8]

    def _normalize_candidate_reviews(self, values: object) -> list[dict[str, object]]:
        if not isinstance(values, list):
            return []
        reviews: list[dict[str, object]] = []
        for value in values:
            if not isinstance(value, dict):
                continue
            mapping_id = str(value.get("mappingId") or "").strip()
            if not mapping_id:
                continue
            reviews.append(
                {
                    "mappingId": mapping_id,
                    "approved": bool(value.get("approved", True)),
                    "riskLevel": self._normalize_risk_level(value.get("riskLevel")),
                    "issue": str(value.get("issue") or "").strip(),
                    "suggestedSheet": str(value.get("suggestedSheet") or "").strip(),
                    "suggestedCell": str(value.get("suggestedCell") or "").strip().upper(),
                }
            )
        return reviews[:50]
