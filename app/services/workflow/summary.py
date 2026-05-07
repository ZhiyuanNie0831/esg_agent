"""最终结果整理服务。

把技能结果、执行日志、证据和下载产物整理成用户可以直接查看的最终输出结构。
"""

import base64
from typing import Any

from app.config import settings
from app.schemas.workflow import (
    WorkflowDownloadItem,
    ExecutionLogEntry,
    IntentionAnalysis,
    MissingDocumentCheck,
    PreparedDocument,
    WorkflowEvidenceItem,
    WorkflowFinalOutput,
)
from app.services.workflow.errors import require_local_fallback
from app.services.workflow.evidence import collect_document_evidence
from app.services.workflow.file_store import workflow_file_store
from app.services.workflow.text import (
    intent_label,
    join_document_kind_labels,
    join_intent_labels,
    join_skill_labels,
    skill_label,
)


class WorkflowSummaryService:
    """把执行结果整理成用户可读的最终输出。"""

    def __init__(
        self,
        agent_runtime: Any | None = None,
        *,
        local_fallback_enabled: bool = True,
        job_id: str | None = None,
        inline_download_content: bool = True,
    ) -> None:
        self._agent_runtime = agent_runtime
        self._local_fallback_enabled = local_fallback_enabled
        self._job_id = job_id
        self._inline_download_content = inline_download_content

    def build_output(
        self,
        task: str,
        intention: IntentionAnalysis,
        documents: list[PreparedDocument],
        missing_documents: MissingDocumentCheck,
        logs: list[ExecutionLogEntry],
        skill_results: dict[str, dict[str, Any]],
    ) -> WorkflowFinalOutput:
        """生成最终输出对象。"""
        next_actions = self._build_next_actions(
            intention=intention,
            documents=documents,
            missing_documents=missing_documents,
            logs=logs,
        )
        evidence = self._build_evidence(
            documents=documents,
            skill_results=skill_results,
        )
        downloads = self._build_downloads(skill_results)
        summary_text = self._build_summary_text(
            task=task,
            intention=intention,
            documents=documents,
            missing_documents=missing_documents,
            logs=logs,
            skill_results=skill_results,
            evidence=evidence,
            downloads=downloads,
        )
        revised_document = self._resolve_revised_document(skill_results)

        agent_output = self._build_output_with_agent(
            task=task,
            intention=intention,
            documents=documents,
            missing_documents=missing_documents,
            logs=logs,
            skill_results=skill_results,
        )
        if agent_output is not None:
            summary_text = str(agent_output.get("summaryText") or summary_text).strip() or summary_text
            next_actions = self._normalize_next_actions(
                agent_output.get("nextActions"),
                fallback=next_actions,
            )
        else:
            require_local_fallback(
                local_fallback_enabled=self._local_fallback_enabled,
                agent_active=self._agent_runtime is not None,
                capability="最终结果整理",
            )

        return WorkflowFinalOutput(
            summaryText=summary_text,
            revisedDocument=revised_document,
            nextActions=next_actions,
            evidence=evidence,
            downloads=downloads,
            artifacts=self._build_artifacts(
                task=task,
                intention=intention,
                missing_documents=missing_documents,
                logs=logs,
                next_actions=next_actions,
                evidence=evidence,
                downloads=downloads,
                skill_results=skill_results,
                agent_participated=bool(agent_output),
            ),
        )

    def _build_next_actions(
        self,
        intention: IntentionAnalysis,
        documents: list[PreparedDocument],
        missing_documents: MissingDocumentCheck,
        logs: list[ExecutionLogEntry],
    ) -> list[str]:
        """根据执行状态推导下一步建议。"""
        if missing_documents.advice:
            return missing_documents.advice

        failed_logs = [log for log in logs if log.status == "failed"]
        if failed_logs:
            return ["检查失败步骤的错误信息，修复输入或技能逻辑后重新执行。"]

        if any(log.status == "blocked" for log in logs):
            return ["先处理前置失败步骤，再重新运行被阻塞的后续步骤。"]

        if intention.documentRequired and not documents:
            return ["补充待处理文档或正文内容后重新规划。"]

        return ["如需调整结果，可补充要求后重新规划或再次执行。"]

    def _build_output_with_agent(
        self,
        *,
        task: str,
        intention: IntentionAnalysis,
        documents: list[PreparedDocument],
        missing_documents: MissingDocumentCheck,
        logs: list[ExecutionLogEntry],
        skill_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        """如 agent 可用，则交给 agent 进一步润色最终总结。"""
        if self._agent_runtime is None:
            return None

        return self._agent_runtime.compose_final_output(
            task=task,
            intention=intention,
            documents=documents,
            missing_documents=missing_documents,
            logs=logs,
            skill_results=skill_results,
        )

    def _normalize_next_actions(self, values: Any, fallback: list[str]) -> list[str]:
        """清洗 agent 返回的下一步建议列表。"""
        if not isinstance(values, list):
            return fallback

        normalized: list[str] = []
        for value in values:
            item = str(value or "").strip()
            if item and item not in normalized:
                normalized.append(item)

        return normalized or fallback

    def _build_summary_text(
        self,
        *,
        task: str,
        intention: IntentionAnalysis,
        documents: list[PreparedDocument],
        missing_documents: MissingDocumentCheck,
        logs: list[ExecutionLogEntry],
        skill_results: dict[str, dict[str, Any]],
        evidence: list[WorkflowEvidenceItem],
        downloads: list[WorkflowDownloadItem],
    ) -> str:
        """拼装默认的最终总结文本。"""
        if missing_documents.missingKinds:
            return (
                f"任务“{task}”暂时还不能执行。"
                f"缺少的文档类型有：{join_document_kind_labels(missing_documents.missingKinds)}。"
            )

        failed_logs = [log for log in logs if log.status == "failed"]
        blocked_logs = [log for log in logs if log.status == "blocked"]
        summary_parts = [
            f"任务类型：{intent_label(intention.intentType)}",
            f"识别意图：{join_intent_labels(intention.detectedIntentTypes)}",
            f"已处理文档数：{len(documents)}",
            f"文档就绪度：{missing_documents.readiness}",
            f"已执行技能：{join_skill_labels(list(skill_results)) if skill_results else '无'}",
            *self._build_skill_highlights(skill_results),
        ]
        if failed_logs:
            summary_parts.append(
                "失败步骤：" + "；".join(f"{log.title}({log.message})" for log in failed_logs)
            )
        if blocked_logs:
            summary_parts.append("未执行步骤：" + "；".join(log.title for log in blocked_logs))
        if missing_documents.advice:
            summary_parts.append("注意事项：" + "；".join(missing_documents.advice))
        if evidence:
            summary_parts.append(
                "关键出处："
                + "；".join(
                    f"{item.title}（{item.document} / {item.location}）"
                    for item in evidence[:3]
                )
            )
        if downloads:
            summary_parts.append(
                "导出文件：" + "；".join(f"{item.label}（{item.filename}）" for item in downloads)
            )
        return "\n\n".join(part for part in summary_parts if part)

    def _build_skill_highlights(self, skill_results: dict[str, dict[str, Any]]) -> list[str]:
        """提取各技能的摘要亮点，避免重复展示。"""
        highlights: list[str] = []
        for _, result in skill_results.items():
            summary = str(result.get("summary", "")).strip()
            if summary and summary not in highlights:
                highlights.append(summary)
        return highlights

    def _resolve_revised_document(self, skill_results: dict[str, dict[str, Any]]) -> str | None:
        """从技能结果里选出适合直接展示的主文稿。"""
        if "esg_report_writer" in skill_results:
            return str(skill_results["esg_report_writer"].get("reportMarkdown") or skill_results["esg_report_writer"].get("revisedDocument"))
        if "document_reviser" in skill_results:
            return str(skill_results["document_reviser"].get("revisedDocument"))
        if "esg_report_outline_builder" in skill_results:
            return str(skill_results["esg_report_outline_builder"].get("outlineMarkdown"))
        if "table_filler" in skill_results:
            return str(skill_results["table_filler"].get("filledTableMarkdown"))
        return None

    def _build_artifacts(
        self,
        *,
        task: str,
        intention: IntentionAnalysis,
        missing_documents: MissingDocumentCheck,
        logs: list[ExecutionLogEntry],
        next_actions: list[str],
        evidence: list[WorkflowEvidenceItem],
        downloads: list[WorkflowDownloadItem],
        skill_results: dict[str, dict[str, Any]],
        agent_participated: bool,
    ) -> dict[str, Any]:
        """构造结构化 artifacts，供前端调试和详情展示。"""
        return {
            "任务": task,
            "任务类型": intent_label(intention.intentType),
            "识别意图": [intent_label(intent_type) for intent_type in intention.detectedIntentTypes],
            "文档就绪度": missing_documents.readiness,
            "已有文档类型": [join_document_kind_labels([kind]) for kind in missing_documents.presentKinds],
            "文档建议": missing_documents.advice,
            "agent参与": agent_participated,
            "执行日志条数": len(logs),
            "执行轨迹": self._build_execution_trace(logs),
            "下一步建议": next_actions,
            "证据出处": [item.model_dump() for item in evidence],
            "导出文件": [
                {
                    "label": item.label,
                    "filename": item.filename,
                    "mimeType": item.mimeType,
                }
                for item in downloads
            ],
            "技能结果": self._sanitize_skill_results_for_artifacts(skill_results),
        }

    def _build_evidence(
        self,
        *,
        documents: list[PreparedDocument],
        skill_results: dict[str, dict[str, Any]],
    ) -> list[WorkflowEvidenceItem]:
        """聚合技能证据和文档级证据，并去重。"""
        collected: list[WorkflowEvidenceItem] = []
        seen_keys: set[tuple[str, str, str, str, str]] = set()

        for skill_name, result in skill_results.items():
            source_step = skill_label(skill_name)
            raw_evidence = result.get("evidenceRefs") or result.get("evidence") or []
            for raw_item in raw_evidence:
                if not isinstance(raw_item, dict):
                    continue
                title = str(raw_item.get("title") or "").strip()
                document_id = str(raw_item.get("documentId") or "").strip() or None
                document = str(raw_item.get("document") or "").strip()
                location = str(raw_item.get("location") or "正文定位未标注").strip()
                excerpt = str(raw_item.get("excerpt") or "").strip()
                if not title or not document or not excerpt:
                    continue
                segment_id = str(raw_item.get("segmentId") or "").strip()
                key = (title, document, location, excerpt, segment_id)
                if key in seen_keys:
                    continue
                collected.append(
                    WorkflowEvidenceItem(
                        title=title,
                        documentId=document_id,
                        document=document,
                        location=location,
                        excerpt=excerpt,
                        sourceStep=str(raw_item.get("sourceStep") or source_step),
                        segmentId=segment_id or None,
                        page=raw_item.get("page"),
                        section=str(raw_item.get("section") or "").strip() or None,
                        sheet=str(raw_item.get("sheet") or "").strip() or None,
                        rowStart=raw_item.get("rowStart"),
                        rowEnd=raw_item.get("rowEnd"),
                        cellRange=str(raw_item.get("cellRange") or "").strip() or None,
                    )
                )
                seen_keys.add(key)

        if collected:
            collected.sort(key=self._evidence_sort_key)
            return collected[:8]

        fallback_items = collect_document_evidence(documents, source_step="输入材料")
        return [WorkflowEvidenceItem(**item) for item in fallback_items[:6]]

    def _build_downloads(self, skill_results: dict[str, dict[str, Any]]) -> list[WorkflowDownloadItem]:
        downloads: list[WorkflowDownloadItem] = []

        for result in skill_results.values():
            for raw_item in result.get("exportFiles", []) or []:
                if not isinstance(raw_item, dict):
                    continue
                artifact_id = str(raw_item.get("artifactId") or "").strip() or None
                download_url = str(raw_item.get("downloadUrl") or "").strip() or None
                content_base64 = str(raw_item.get("contentBase64") or "").strip() or None

                if not artifact_id and content_base64:
                    artifact = workflow_file_store.store_artifact(
                        job_id=self._job_id,
                        label=str(raw_item.get("label") or "下载文件"),
                        filename=str(raw_item.get("filename") or "workflow_export.bin"),
                        mime_type=str(raw_item.get("mimeType") or "application/octet-stream"),
                        data=base64.b64decode(content_base64),
                    )
                    artifact_id = str(artifact.get("artifactId") or "").strip() or None
                    download_url = str(artifact.get("downloadUrl") or "").strip() or None

                if not artifact_id and not content_base64:
                    continue
                downloads.append(
                    WorkflowDownloadItem(
                        label=str(raw_item.get("label") or "下载文件"),
                        filename=str(raw_item.get("filename") or "workflow_export.bin"),
                        mimeType=str(raw_item.get("mimeType") or "application/octet-stream"),
                        artifactId=artifact_id,
                        downloadUrl=download_url,
                        contentBase64=content_base64 if self._inline_download_content else None,
                    )
                )

        return downloads[:4]

    def _sanitize_skill_results_for_artifacts(
        self,
        skill_results: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        sanitized: dict[str, dict[str, Any]] = {}

        for skill_name, result in skill_results.items():
            sanitized_result = dict(result)
            export_files = sanitized_result.get("exportFiles")
            if isinstance(export_files, list):
                sanitized_result["exportFiles"] = [
                    {
                        "label": str(item.get("label") or "下载文件"),
                        "filename": str(item.get("filename") or "workflow_export.bin"),
                        "mimeType": str(item.get("mimeType") or "application/octet-stream"),
                        "artifactId": str(item.get("artifactId") or "").strip() or None,
                        "downloadUrl": str(item.get("downloadUrl") or "").strip() or None,
                    }
                    for item in export_files
                    if isinstance(item, dict)
                ]
            sanitized[skill_name] = sanitized_result

        return sanitized

    def _evidence_sort_key(self, item: WorkflowEvidenceItem) -> tuple[int, int, str]:
        location_score = sum(
            1
            for value in (
                item.segmentId,
                item.page,
                item.sheet,
                item.rowStart,
                item.rowEnd,
                item.cellRange,
                item.section,
            )
            if value not in (None, "")
        )
        return (-location_score, len(item.excerpt), item.title)

    def _build_execution_trace(self, logs: list[ExecutionLogEntry]) -> list[dict[str, Any]]:
        return [
            {
                "步骤": f"{log.stepNumber}. {log.title}",
                "类型": self._map_log_kind(log.kind),
                "执行方": self._map_executor(log.executor),
                "状态": log.status,
                "消息": log.message,
                "依赖步骤": list(log.dependsOn),
                "开始时间": log.startedAt.isoformat(),
                "结束时间": log.finishedAt.isoformat() if log.finishedAt else None,
                "耗时毫秒": log.durationMs,
                "输入摘要": log.inputSummary,
                "输出摘要": log.outputSummary,
                "输出预览": log.outputPreview,
            }
            for log in logs
        ]

    def _map_log_kind(self, kind: str) -> str:
        if kind == "system":
            return "系统步骤"
        if kind == "checkpoint":
            return "人工确认"
        if kind == "skill":
            return "技能执行"
        return kind

    def _map_executor(self, executor: str | None) -> str:
        if executor == "workflow_system":
            return "工作流系统"
        if executor == "human_review":
            return "人工确认"
        if executor in {"model_api_agent", "openai_agent"}:
            return f"{settings.model_api_provider_label} Agent"
        if executor == "local_skill":
            return "本地技能"
        if executor == "agent":
            return "Agent"
        return executor or "-"
