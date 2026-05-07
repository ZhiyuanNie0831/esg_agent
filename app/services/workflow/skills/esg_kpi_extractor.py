"""ESG 指标提取技能。"""

from app.services.workflow.esg import (
    build_esg_indicator_evidence,
    build_esg_indicator_summary,
    extract_esg_indicators,
)
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class ESGKPIExtractorSkill(WorkflowSkill):
    """从材料中抽取 ESG 量化指标。"""

    name = "esg_kpi_extractor"
    title = "提取 ESG 指标"
    description = "从 ESG 材料中提取常见量化指标、数值和来源片段。"
    input_hint = "标准化后的 ESG 文档和片段"
    output_hint = "ESG 指标列表"
    tags = ("esg", "kpi", "extract")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        """输出指标列表、数量和证据。"""
        indicators = extract_esg_indicators(context.documents)
        return {
            "summary": build_esg_indicator_summary(indicators),
            "indicators": indicators,
            "indicatorCount": len(indicators),
            "evidence": build_esg_indicator_evidence(indicators, source_step=self.title),
            "evidenceRefs": build_esg_indicator_evidence(indicators, source_step=self.title),
        }
