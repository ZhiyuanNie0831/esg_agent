"""表格计算计划技能。"""

from __future__ import annotations

from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill
from app.services.workflow.skills.spreadsheet_calculator import SpreadsheetCalculatorSkill


class CalculationPlannerSkill(WorkflowSkill):
    """在执行计算前，把自然语言任务转成可审计的计算计划。"""

    name = "calculation_planner"
    title = "规划表格计算"
    description = "根据任务语义、源数据 workbook 和表头，生成后续计算步骤要执行的列、操作和分组计划。"
    input_hint = "Excel 角色识别结果、任务描述和源数据结构"
    output_hint = "结构化计算计划，包含 source sheet、数值列、操作和可选分组字段"
    tags = ("excel", "spreadsheet", "calculate", "workflow")

    def __init__(self) -> None:
        self._calculator = SpreadsheetCalculatorSkill()

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        tables = self._calculator._collect_tables(context)
        if not tables:
            return {
                "summary": "当前没有可用于生成计算计划的源数据表。",
                "calculations": [],
                "calculationPlan": {"calculations": []},
            }

        task_lower = context.task.lower()
        operations = self._calculator._detect_operations(task_lower)
        time_tokens = self._calculator._extract_time_tokens(task_lower)
        calculations: list[dict[str, object]] = []

        for table in tables:
            numeric_columns = list(table["numericColumns"])
            if not numeric_columns:
                continue

            headers = list(table["headers"])
            target_columns = self._calculator._match_headers(task_lower, numeric_columns) or numeric_columns
            group_by = self._calculator._match_group_by(task_lower, headers, numeric_columns)

            for column in target_columns:
                for operation in operations:
                    calculations.append(
                        {
                            "calculationId": f"calc_{len(calculations) + 1}",
                            "sourceDocumentId": table.get("documentId"),
                            "sourceWorkbook": table["document"],
                            "sourceSheet": table["sheet"],
                            "column": column,
                            "operation": operation,
                            "groupBy": group_by,
                            "filters": {"timeTokens": time_tokens},
                            "label": self._build_calculation_label(
                                column=str(column),
                                operation=str(operation),
                                group_by=str(group_by or ""),
                            ),
                        }
                    )

        if not calculations:
            return {
                "summary": "已读取源数据，但没有识别到需要计算的数值列。",
                "calculations": [],
                "calculationPlan": {"calculations": []},
            }

        summary = (
            f"已生成 {len(calculations)} 个表格计算计划："
            + "；".join(
                f"{item['sourceWorkbook']} / {item['sourceSheet']} / {item['column']} -> {item['operation']}"
                for item in calculations[:5]
            )
        )
        if len(calculations) > 5:
            summary += f"；其余 {len(calculations) - 5} 个计划保留在结构化输出中。"

        return {
            "summary": summary,
            "operations": operations,
            "timeTokens": time_tokens,
            "calculations": calculations,
            "calculationPlan": {"calculations": calculations},
        }

    def _build_calculation_label(self, *, column: str, operation: str, group_by: str) -> str:
        operation_labels = {
            "sum": "合计",
            "avg": "平均值",
            "max": "最大值",
            "min": "最小值",
            "count": "数量",
            "ratio": "占比",
            "intensity": "强度",
            "yoy": "同比",
            "mom": "环比",
        }
        label = f"{column}{operation_labels.get(operation, operation)}"
        return f"按{group_by}{label}" if group_by else label
