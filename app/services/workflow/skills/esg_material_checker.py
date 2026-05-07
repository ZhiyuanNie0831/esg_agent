"""ESG 材料完整度检查技能。"""

from app.services.workflow.esg import build_esg_material_summary, build_esg_topic_evidence, collect_esg_coverage
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class ESGMaterialCheckerSkill(WorkflowSkill):
    """检查 ESG 三大支柱和主题覆盖情况。"""

    name = "esg_material_checker"
    title = "检查 ESG 材料"
    description = "按环境、社会、治理三大支柱检查材料覆盖度，并提示明显缺口。"
    input_hint = "标准化后的 ESG 文档列表"
    output_hint = "ESG 材料覆盖与缺口"
    tags = ("esg", "check", "coverage")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        """输出 ESG 覆盖结果、缺口和建议。"""
        coverage = collect_esg_coverage(context.documents)
        recommendations = []
        if coverage["missingPillars"]:
            recommendations.append("优先补充缺失支柱对应的证明材料、政策或量化数据。")
        if not coverage["topicCoverage"]:
            recommendations.append("当前材料缺少明确 ESG 主题内容，建议补充正文或 OCR 结果。")

        return {
            "summary": build_esg_material_summary(coverage),
            "pillarCoverage": coverage["pillarCoverage"],
            "missingPillars": coverage["missingPillars"],
            "topicCoverage": coverage["topicCoverage"],
            "topicMatrix": coverage["topicMatrix"],
            "recommendedDocumentKinds": coverage["recommendedDocumentKinds"],
            "recommendations": recommendations,
            "evidence": build_esg_topic_evidence(coverage["topicMatrix"], source_step=self.title),
            "evidenceRefs": build_esg_topic_evidence(coverage["topicMatrix"], source_step=self.title),
        }
