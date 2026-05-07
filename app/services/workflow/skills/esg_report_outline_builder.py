"""ESG 报告大纲生成技能。"""

from app.services.workflow.esg import build_esg_outline, build_esg_topic_evidence, collect_esg_coverage
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class ESGReportOutlineBuilderSkill(WorkflowSkill):
    """根据现有 ESG 材料生成报告大纲。"""

    name = "esg_report_outline_builder"
    title = "生成 ESG 报告大纲"
    description = "基于现有 ESG 材料生成章节大纲、关键主题和建议补充项。"
    input_hint = "标准化后的 ESG 文档和片段"
    output_hint = "ESG 报告大纲 Markdown"
    tags = ("esg", "outline", "report")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        """输出大纲、缺口和建议补充项。"""
        outline = build_esg_outline(context.documents)
        coverage = collect_esg_coverage(context.documents)
        recommendations = outline["recommendations"] or ["可在此大纲基础上补充量化数据和案例。"]
        return {
            "summary": "已生成 ESG 报告大纲，并整理建议补充项。",
            "outlineMarkdown": outline["outlineMarkdown"],
            "coveredTopics": outline["coveredTopics"],
            "missingPillars": outline["missingPillars"],
            "topicMatrix": outline["topicMatrix"],
            "recommendations": recommendations,
            "evidence": build_esg_topic_evidence(coverage["topicMatrix"], source_step=self.title),
            "evidenceRefs": build_esg_topic_evidence(coverage["topicMatrix"], source_step=self.title),
        }
