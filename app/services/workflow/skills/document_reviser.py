"""文档修订技能。

优先调用 agent 生成修订稿；若 agent 不可用，则使用本地规则拼装基础草稿。
"""

from app.services.workflow.evidence import collect_document_evidence
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class DocumentReviserSkill(WorkflowSkill):
    """根据任务目标整理更清晰的修订稿。"""

    name = "document_reviser"
    title = "修订草稿"
    description = "根据任务描述和文档摘录整理出一版更清晰的草稿。"
    input_hint = "标准化后的文档列表和任务描述"
    output_hint = "修订后的 Markdown 文档"
    requires_approval = True
    tags = ("documents", "revise")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        """生成修订稿，并附带来源证据。"""
        documents, document_context = context.build_document_context(
            max_documents=3,
            max_segments_per_document=3,
            max_total_segments=12,
            segment_text_limit=320,
        )
        evidence = collect_document_evidence(documents, source_step=self.title)
        if context.agent_runtime is not None:
            revised_document = context.agent_runtime.revise_documents(
                task=context.task,
                documents=documents,
            )
            if revised_document:
                return {"revisedDocument": revised_document, "source": "agent", "evidence": evidence, "evidenceRefs": evidence}
        context.require_local_fallback("文稿修订")

        excerpts = [
            f"## {document['name']}\n{_build_document_body(document)[:900]}"
            for document in document_context.get("documents", [])
        ]
        body_sections = excerpts or ["当前没有提供可用的原始文档。"]
        revised_document = "\n\n".join(
            [
                "# 修订稿",
                f"任务：{context.task}",
                "## 整理内容",
                *body_sections,
            ]
        )

        return {"revisedDocument": revised_document, "evidence": evidence, "evidenceRefs": evidence}


def _build_document_body(document: dict[str, object]) -> str:
    blocks = []
    for segment in document.get("selectedSegments", [])[:3]:
        segment_text = str(segment.get("text") or "").strip()
        if not segment_text:
            continue
        location = _build_segment_heading(segment)
        blocks.append(f"### {location}\n{segment_text}" if location else segment_text)
    return "\n\n".join(blocks).strip() or str(document.get("textPreview") or "").strip()


def _build_segment_heading(segment: dict[str, object]) -> str:
    heading_parts: list[str] = []
    if segment.get("sheet"):
        heading_parts.append(f"工作表 {segment['sheet']}")
    if segment.get("page") is not None:
        heading_parts.append(f"第 {segment['page']} 页")
    if segment.get("section"):
        heading_parts.append(str(segment["section"]))
    if not heading_parts and segment.get("label"):
        heading_parts.append(str(segment["label"]))
    return " / ".join(heading_parts)
