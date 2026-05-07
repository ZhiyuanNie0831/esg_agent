"""模型 API agent 运行时封装。

把工作流里的若干可选 agent 能力封装成统一接口，例如意图分析、摘要、修订和最终总结。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import settings
from app.services.model_api import ModelApiConfig, build_model_api_gateway
from app.schemas.workflow import (
    ExecutionLogEntry,
    IntentionAnalysis,
    MissingDocumentCheck,
    PreparedDocument,
    SkillDescriptor,
)
from app.services.workflow.evidence import collect_document_evidence
from app.services.workflow.segments import serialize_documents_for_task

SUPPORTED_INTENT_TYPES = ("review", "count", "summarize", "revise", "check_missing", "general")
SUPPORTED_DOCUMENT_KINDS = ("invoice", "receipt", "contract", "statement", "resume", "report", "general")

logger = logging.getLogger(__name__)


class WorkflowModelAgentRuntime:
    """基于模型 API 的可选工作流 agent 运行时。"""

    def __init__(self) -> None:
        self._client = build_model_api_gateway(
            ModelApiConfig(
                provider=settings.model_api_provider,
                api_key=settings.model_api_key,
                base_url=settings.model_api_base_url,
                timeout_seconds=settings.model_api_timeout_seconds,
                protocol=settings.model_api_protocol,
            )
        )
        self._enabled = self._client.enabled and settings.model_api_agent_enabled

    @property
    def enabled(self) -> bool:
        """判断当前 agent 运行时是否真的可用。"""
        return self._enabled and self._client is not None

    def analyze_workflow(
        self,
        task: str,
        documents: list[PreparedDocument],
        preferred_skills: list[str],
        available_skills: list[SkillDescriptor],
    ) -> dict[str, Any] | None:
        """调用 agent 做任务意图分析和技能推荐。"""
        if not self.enabled:
            return None

        payload = {
            "task": task,
            "preferredSkills": preferred_skills,
            "documentContext": serialize_documents_for_task(
                task,
                documents,
                max_documents=8,
                max_segments_per_document=3,
                max_total_segments=16,
                segment_text_limit=420,
            ),
            "availableSkills": [
                {
                    "name": skill.name,
                    "title": skill.title,
                    "description": skill.description,
                    "requiresApproval": skill.requiresApproval,
                    "tags": skill.tags,
                }
                for skill in available_skills
            ],
        }
        instructions = (
            "你是一个工作流编排 agent。"
            "你的任务是分析用户目标、判断是否依赖材料、识别缺失文档类型，并从可用技能中选择最合适的执行顺序。"
            "优先参考 documentContext.documents 中的 selectedSegments，而不是只看 textPreview。"
            "只返回 JSON，不要输出解释文字。"
            "intentType 和 detectedIntentTypes 只能使用这些值："
            f"{', '.join(SUPPORTED_INTENT_TYPES)}。"
            "requiredDocumentKinds 只能使用这些值："
            f"{', '.join(SUPPORTED_DOCUMENT_KINDS)}。"
            "recommendedSkills 只能从 availableSkills.name 中选择。"
            "优先理解用户真正要的最终产物，而不是机械套关键词。"
            "JSON 结构必须包含："
            '{"intentType": "...", "detectedIntentTypes": [], "confidence": 0.0, '
            '"documentRequired": true, "requiredDocumentKinds": [], "recommendedSkills": [], "notes": []}'
        )
        return self._request_json(
            instructions=instructions,
            payload=payload,
            max_output_tokens=1200,
            operation_name="analyze_workflow",
            reasoning_effort=settings.model_api_reasoning_effort,
        )

    def summarize_documents(self, task: str, documents: list[PreparedDocument]) -> str | None:
        """调用 agent 生成文档摘要。"""
        if not self.enabled or not documents:
            return None

        payload = {
            "task": task,
            "documentContext": serialize_documents_for_task(
                task,
                documents,
                max_documents=8,
                max_segments_per_document=5,
                max_total_segments=24,
                segment_text_limit=900,
            ),
        }
        instructions = (
            "你是一个文档总结 agent。"
            "请直接回答用户任务，不要只做材料罗列。"
            "输出要像高水平顾问或分析师写的结果，简洁但有判断。"
            "不要虚构材料中不存在的信息。"
            "如果有多份文件，优先归纳整体结论、关键数字和风险点。"
            "优先使用 selectedSegments 中的原文片段，不要忽略片段上的 page、sheet、section 等来源信息。"
            "如提到关键结论或数字，尽量顺手说明对应文件名或片段位置。"
            "先给结论，再补关键依据。"
        )
        return self._request_text(
            instructions=instructions,
            payload=payload,
            max_output_tokens=1200,
            operation_name="summarize_documents",
            reasoning_effort=settings.model_api_heavy_reasoning_effort,
        )

    def revise_documents(self, task: str, documents: list[PreparedDocument]) -> str | None:
        """调用 agent 生成修订稿。"""
        if not self.enabled:
            return None

        payload = {
            "task": task,
            "documentContext": serialize_documents_for_task(
                task,
                documents,
                max_documents=6,
                max_segments_per_document=6,
                max_total_segments=28,
                segment_text_limit=1200,
            ),
        }
        instructions = (
            "你是一个文稿修订 agent。"
            "请根据任务要求和提供的原始材料，输出一版更清晰、结构化的 Markdown 修订稿。"
            "不要输出解释，只输出最终文稿。"
            "如信息不足，也要保持谨慎表达，不要编造事实。"
            "优先基于 selectedSegments 的内容组织文稿，避免只依赖文件开头的摘要。"
            "涉及关键事实或数字时，保留来源表述空间，不要脱离原文扩写。"
            "文风要求专业、利落、有层次，不要模板腔。"
        )
        return self._request_text(
            instructions=instructions,
            payload=payload,
            max_output_tokens=3000,
            operation_name="revise_documents",
            reasoning_effort=settings.model_api_heavy_reasoning_effort,
        )

    def write_esg_report(
        self,
        *,
        task: str,
        documents: list[PreparedDocument],
        report_context: dict[str, Any],
        requirements: dict[str, Any],
    ) -> str | None:
        """调用 agent 基于材料和 ESG 中间结果生成报告正文。"""
        if not self.enabled or not documents:
            return None

        target_word_count = int(requirements.get("targetWordCount") or 3000)
        max_output_tokens = min(12000, max(2400, int(target_word_count * 1.8)))
        payload = {
            "task": task,
            "requirements": requirements,
            "documentContext": serialize_documents_for_task(
                task,
                documents,
                max_documents=12,
                max_segments_per_document=8,
                max_total_segments=48,
                segment_text_limit=1100,
            ),
            "esgContext": {
                "standards": report_context.get("standards", []),
                "matrixStats": report_context.get("matrixStats", {}),
                "disclosureMatrix": list(report_context.get("disclosureMatrix", []) or [])[:60],
                "indicators": list(report_context.get("indicators", []) or [])[:30],
                "evidenceLinks": list(report_context.get("evidenceLinks", []) or [])[:30],
                "outlineMarkdown": str(report_context.get("outlineMarkdown") or "")[:5000],
            },
        }
        instructions = (
            "你是 ESG 报告撰写 agent。"
            "请基于上传材料、披露矩阵、KPI 和证据索引，生成一份可审阅的 Markdown ESG 报告正文。"
            f"目标字数是 {requirements.get('description') or target_word_count}，"
            f"尽量控制在 {requirements.get('minWordCount')} 到 {requirements.get('maxWordCount')} 字之间。"
            "报告必须包含：报告说明、管理层摘要、环境、社会、治理、关键绩效指标、数据缺口与后续动作、证据索引。"
            "关键事实和数字必须来自材料或 esgContext；材料不足时写“待补充”，不要编造。"
            "语言要专业、正式、适合给客户作为报告初稿审阅。"
            "不要输出解释文字，不要包裹代码块，只输出最终 Markdown 报告。"
        )
        return self._request_text(
            instructions=instructions,
            payload=payload,
            max_output_tokens=max_output_tokens,
            operation_name="write_esg_report",
            reasoning_effort=settings.model_api_heavy_reasoning_effort,
        )

    def compose_final_output(
        self,
        task: str,
        intention: IntentionAnalysis,
        documents: list[PreparedDocument],
        missing_documents: MissingDocumentCheck,
        logs: list[ExecutionLogEntry],
        skill_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        """调用 agent 生成最终总结和下一步建议。"""
        if not self.enabled:
            return None

        payload = {
            "task": task,
            "intention": {
                "intentType": intention.intentType,
                "detectedIntentTypes": intention.detectedIntentTypes,
                "documentRequired": intention.documentRequired,
            },
            "documentContext": serialize_documents_for_task(
                task,
                documents,
                max_documents=8,
                max_segments_per_document=4,
                max_total_segments=20,
                segment_text_limit=820,
            ),
            "documents": [self._serialize_document_summary(document) for document in documents],
            "missingDocuments": {
                "readiness": missing_documents.readiness,
                "missingKinds": missing_documents.missingKinds,
                "advice": missing_documents.advice,
            },
            "logs": [
                {
                    "stepNumber": log.stepNumber,
                    "title": log.title,
                    "status": log.status,
                    "message": log.message,
                }
                for log in logs
            ],
            "evidence": self._build_evidence_context(documents, skill_results),
            "skillResults": self._serialize_skill_results(skill_results),
        }
        instructions = (
            "你是一个工作流结果整理 agent。"
            "请基于任务、文档片段、执行日志、证据和技能结果，输出一个真正能给终端用户看的最终回答。"
            "summaryText 必须先直接回答用户问题，再提炼最重要的依据、数字、风险或下一步。"
            "语言要专业、明确、有压缩感，不要像系统日志汇总。"
            "只返回 JSON，不要输出额外说明。"
            'JSON 结构必须包含：{"summaryText": "...", "nextActions": ["...", "..."]}。'
            "summaryText 用中文概括当前结论；nextActions 给出 1 到 3 条明确下一步建议。"
        )
        return self._request_json(
            instructions=instructions,
            payload=payload,
            max_output_tokens=1600,
            operation_name="compose_final_output",
            reasoning_effort=settings.model_api_heavy_reasoning_effort,
        )

    def _request_text(
        self,
        *,
        instructions: str,
        payload: dict[str, Any],
        max_output_tokens: int,
        operation_name: str,
        reasoning_effort: str | None = None,
    ) -> str | None:
        """向模型 API 请求纯文本结果。"""
        if not self._client.enabled:
            return None

        try:
            text = self._client.request_text(
                model=settings.model_api_model,
                instructions=instructions,
                input_payload=json.dumps(payload, ensure_ascii=False),
                max_output_tokens=max_output_tokens,
                reasoning_effort=reasoning_effort or settings.model_api_reasoning_effort,
            )
        except Exception:
            logger.exception(
                "workflow agent request failed: provider=%s operation=%s model=%s max_output_tokens=%s",
                settings.model_api_provider,
                operation_name,
                settings.model_api_model,
                max_output_tokens,
            )
            return None

        if not text:
            logger.warning(
                "workflow agent returned empty output: provider=%s operation=%s model=%s",
                settings.model_api_provider,
                operation_name,
                settings.model_api_model,
            )
        return text or None

    def _request_json(
        self,
        *,
        instructions: str,
        payload: dict[str, Any],
        max_output_tokens: int,
        operation_name: str,
        reasoning_effort: str | None = None,
    ) -> dict[str, Any] | None:
        """请求 JSON 结果，并对返回文本做 JSON 提取与解析。"""
        raw_text = self._request_text(
            instructions=instructions,
            payload=payload,
            max_output_tokens=max_output_tokens,
            operation_name=operation_name,
            reasoning_effort=reasoning_effort,
        )
        if not raw_text:
            return None

        json_fragment = self._extract_json_fragment(raw_text)
        if not json_fragment:
            logger.warning(
                "workflow agent json extraction failed: operation=%s raw_preview=%s",
                operation_name,
                raw_text[:200],
            )
            return None

        try:
            parsed = json.loads(json_fragment)
        except json.JSONDecodeError:
            logger.warning(
                "workflow agent json parsing failed: operation=%s raw_preview=%s",
                operation_name,
                json_fragment[:200],
            )
            return None

        return parsed if isinstance(parsed, dict) else None

    def _extract_json_fragment(self, text: str) -> str:
        """从可能包裹在代码块中的返回文本里提取 JSON 片段。"""
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
            stripped = "\n".join(lines).strip()

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            return ""

        return stripped[start : end + 1]

    def _serialize_skill_results(self, skill_results: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """裁剪技能结果，只保留适合发给 agent 的摘要信息。"""
        serialized: dict[str, dict[str, Any]] = {}

        for skill_name, result in skill_results.items():
            serialized[skill_name] = {
                "summary": str(result.get("summary", ""))[:1200],
                "revisedDocument": str(result.get("revisedDocument", ""))[:1200],
                "reportMarkdown": str(result.get("reportMarkdown", ""))[:1600],
                "filledTableMarkdown": str(result.get("filledTableMarkdown", ""))[:1200],
                "keys": sorted(result),
            }

        return serialized

    def _serialize_document_summary(self, document: PreparedDocument) -> dict[str, Any]:
        return {
            "name": document.name,
            "type": document.type,
            "textPreview": document.textPreview,
            "inferredKinds": document.inferredKinds,
            "segmentCount": len(document.segments),
        }

    def _build_evidence_context(
        self,
        documents: list[PreparedDocument],
        skill_results: dict[str, dict[str, Any]],
    ) -> list[dict[str, str]]:
        evidence_items: list[dict[str, str]] = []

        for result in skill_results.values():
            for item in result.get("evidence", []) or []:
                if isinstance(item, dict):
                    evidence_items.append(
                        {
                            "title": str(item.get("title") or "").strip(),
                            "document": str(item.get("document") or "").strip(),
                            "location": str(item.get("location") or "").strip(),
                            "excerpt": str(item.get("excerpt") or "").strip()[:320],
                        }
                    )

        if evidence_items:
            return evidence_items[:8]

        return collect_document_evidence(documents, max_items=6, source_step="输入材料")


# 兼容旧导入路径，避免外部代码升级时直接报错。
WorkflowOpenAIAgentRuntime = WorkflowModelAgentRuntime
