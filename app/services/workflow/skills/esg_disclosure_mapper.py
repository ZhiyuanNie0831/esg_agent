"""ESG 披露主题映射技能。"""

from app.services.workflow.esg import build_esg_topic_evidence, collect_esg_coverage
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class ESGDisclosureMapperSkill(WorkflowSkill):
    """把材料映射到 ESG 主题覆盖结果。"""

    name = "esg_disclosure_mapper"
    title = "映射 ESG 披露主题"
    description = "把材料内容映射到环境、社会、治理披露主题，识别已覆盖主题和空白区。"
    input_hint = "标准化后的 ESG 文档和片段"
    output_hint = "ESG 披露主题映射结果"
    tags = ("esg", "mapping", "disclosure")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        """输出 ESG 主题覆盖和证据。"""
        coverage = collect_esg_coverage(context.documents)
        topic_names = [topic["label"] for topic in coverage["topicMatrix"] if topic["status"] != "missing"]
        summary = (
            "已映射 ESG 披露主题："
            + ("、".join(topic_names[:8]) if topic_names else "当前未识别到明确主题")
            + "。"
        )

        return {
            "summary": summary,
            "pillarCoverage": coverage["pillarCoverage"],
            "topicCoverage": coverage["topicCoverage"],
            "topicMatrix": coverage["topicMatrix"],
            "mappedTopicCount": len(coverage["topicCoverage"]),
            "evidence": build_esg_topic_evidence(coverage["topicMatrix"], source_step=self.title),
            "evidenceRefs": build_esg_topic_evidence(coverage["topicMatrix"], source_step=self.title),
        }
