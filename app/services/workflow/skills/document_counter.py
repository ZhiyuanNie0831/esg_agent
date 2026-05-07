"""文档统计技能。"""

from collections import Counter

from app.services.workflow.evidence import collect_document_evidence
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class DocumentCounterSkill(WorkflowSkill):
    """统计文档数量、类型和业务类别。"""

    name = "document_counter"
    title = "统计文档"
    description = "按文档类型和识别出的业务类别做数量统计。"
    input_hint = "标准化后的文档列表"
    output_hint = "按文档类型和文档类别统计的数量"
    tags = ("documents", "count")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        """输出按类型和业务类别聚合的统计结果。"""
        type_counter = Counter(document.type for document in context.documents)
        kind_counter = Counter(kind for document in context.documents for kind in document.inferredKinds)

        evidence = collect_document_evidence(context.documents, source_step=self.title)
        return {
            "总文档数": len(context.documents),
            "按类型统计": dict(type_counter),
            "按类别统计": dict(kind_counter),
            "evidence": evidence,
            "evidenceRefs": evidence,
        }
