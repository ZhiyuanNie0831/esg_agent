"""ESG 标准选择技能。"""

from app.services.workflow.esg import select_esg_standards
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class ESGStandardSelectorSkill(WorkflowSkill):
    """选择 ESG 报告优先对齐的披露标准。"""

    name = "esg_standard_selector"
    title = "选择 ESG 标准"
    description = "根据任务和材料判断 ESG 报告应优先对齐 GRI、ISSB、ESRS 或本地交易所要求。"
    input_hint = "任务描述和已上传 ESG 材料"
    output_hint = "建议适用的 ESG 披露标准及选择理由"
    tags = ("esg", "standard", "report")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        selection = select_esg_standards(context.task, context.documents)
        standards = selection.get("standards", [])
        names = "、".join(str(item.get("code") or "") for item in standards if isinstance(item, dict))
        return {
            "summary": f"已选择 ESG 披露标准：{names or 'GRI'}。",
            **selection,
        }
