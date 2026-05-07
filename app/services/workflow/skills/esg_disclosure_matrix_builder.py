"""ESG 披露矩阵构建技能。"""

from app.services.workflow.esg import build_esg_disclosure_matrix, build_esg_topic_evidence
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class ESGDisclosureMatrixBuilderSkill(WorkflowSkill):
    """把标准要求、主题覆盖和缺口组织成披露矩阵。"""

    name = "esg_disclosure_matrix_builder"
    title = "构建 ESG 披露矩阵"
    description = "按选定标准建立披露项矩阵，标注 covered / weak / missing、所需数据和下一步动作。"
    input_hint = "ESG 标准选择结果、主题覆盖结果和材料证据"
    output_hint = "披露矩阵、覆盖统计和缺口说明"
    tags = ("esg", "disclosure", "matrix")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        standards = context.previous_results.get("esg_standard_selector", {}).get("standards", [])
        matrix = build_esg_disclosure_matrix(
            context.documents,
            standards=standards if isinstance(standards, list) else [],
        )
        stats = matrix["stats"]
        summary = (
            "已构建 ESG 披露矩阵："
            f"covered {stats['covered']} / weak {stats['weak']} / missing {stats['missing']}。"
        )
        evidence = build_esg_topic_evidence(matrix["coverage"]["topicMatrix"], source_step=self.title)
        return {
            "summary": summary,
            "disclosureMatrix": matrix["matrix"],
            "matrixStats": stats,
            "standards": matrix["standards"],
            "evidence": evidence,
            "evidenceRefs": evidence,
        }
