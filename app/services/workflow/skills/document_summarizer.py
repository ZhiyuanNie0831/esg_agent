"""文档总结技能。"""

from app.services.workflow.evidence import collect_document_evidence
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class DocumentSummarizerSkill(WorkflowSkill):
    """围绕当前任务生成文档摘要。"""

    name = "document_summarizer"
    title = "总结文档"
    description = "基于当前文档内容生成简洁的总结。"
    input_hint = "标准化后的文档列表"
    output_hint = "简短总结文本"
    tags = ("documents", "summary")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        """优先调用 agent，总结失败时回退到本地摘要。"""
        documents, document_context = context.build_document_context(
            max_documents=6,
            max_segments_per_document=2,
            max_total_segments=10,
            segment_text_limit=220,
        )
        evidence = collect_document_evidence(documents, source_step=self.title)
        if not documents:
            return {
                "summary": "当前没有可用文档，因此只能基于任务本身做简要总结。",
                "evidence": evidence,
                "evidenceRefs": evidence,
            }

        if context.agent_runtime is not None:
            agent_summary = context.agent_runtime.summarize_documents(
                task=context.task,
                documents=documents,
            )
            if agent_summary:
                return {"summary": agent_summary, "source": "agent", "evidence": evidence, "evidenceRefs": evidence}
        context.require_local_fallback("文档总结")

        lines = [
            f"{index}. {document['name']}：{_build_document_excerpt(document)[:260]}"
            for index, document in enumerate(document_context.get("documents", []), start=1)
        ]
        summary = "\n".join(lines[:6])

        return {"summary": summary, "evidence": evidence, "evidenceRefs": evidence}


def _build_document_excerpt(document: dict[str, object]) -> str:
    excerpts = []
    for segment in document.get("selectedSegments", [])[:2]:
        segment_text = str(segment.get("text") or "").strip()
        if not segment_text:
            continue
        location = _build_segment_location(segment)
        excerpts.append(f"{location}：{segment_text}" if location else segment_text)
    return " ".join(excerpts).strip() or str(document.get("textPreview") or "").strip()


def _build_segment_location(segment: dict[str, object]) -> str:
    location_parts: list[str] = []
    if segment.get("page") is not None:
        location_parts.append(f"第 {segment['page']} 页")
    if segment.get("sheet"):
        location_parts.append(f"工作表 {segment['sheet']}")
    if segment.get("section"):
        location_parts.append(str(segment["section"]))
    return " / ".join(location_parts)
