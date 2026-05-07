"""文档读取技能。

把标准化文档列表整理成简短预览，便于后续步骤快速了解输入范围。
"""

from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill
from app.services.workflow.evidence import collect_document_evidence


class DocumentReaderSkill(WorkflowSkill):
    """输出文档基础信息、预览和证据片段。"""

    name = "document_reader"
    title = "读取文档"
    description = "读取已经标准化的文档，并为后续步骤提供文档预览。"
    input_hint = "标准化后的文档列表"
    output_hint = "文档预览和提取出的文本片段"
    tags = ("documents", "read")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        """读取文档列表并生成预览结果。"""
        documents = [
            {
                "name": document.name,
                "type": document.type,
                "usedOcr": document.usedOcr,
                "preview": document.textPreview,
                "segmentCount": len(document.segments),
                "kinds": document.inferredKinds,
            }
            for document in context.documents
        ]
        combined_preview = "\n".join(
            f"- {document['name']}：{document['preview']}" for document in documents[:5]
        ) or "当前没有提供任何文档。"

        evidence = collect_document_evidence(context.documents, source_step=self.title)
        return {
            "文档数量": len(documents),
            "文档列表": documents,
            "合并预览": combined_preview,
            "evidence": evidence,
            "evidenceRefs": evidence,
        }
