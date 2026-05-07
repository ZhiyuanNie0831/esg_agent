"""Excel 角色识别技能。"""

from __future__ import annotations

from app.services.workflow.excel_roles import classify_excel_documents
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class ExcelRoleClassifierSkill(WorkflowSkill):
    """判断 Excel workflow 中哪些 workbook 是源数据，哪些是待填模板。"""

    name = "excel_role_classifier"
    title = "识别 Excel 角色"
    description = "识别上传的 Excel 中哪份更像原始数据，哪份更像待填模板。"
    input_hint = "任务描述和已解析的 Excel 文档结构"
    output_hint = "源数据 workbook、模板 workbook、角色置信度和识别原因"
    tags = ("excel", "spreadsheet", "workflow", "fill")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        result = classify_excel_documents(context.task, context.documents)
        return {
            **result,
            "executor": "local_skill",
        }
