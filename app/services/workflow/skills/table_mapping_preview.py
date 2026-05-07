"""填表映射预览技能。

位于 `spreadsheet_calculator` 之后、`table_filler` 之前。
负责根据计算结果预估最可能的目标 sheet / cell，供人工确认前编辑。
"""

from __future__ import annotations

from app.services.workflow.excel_roles import filter_documents_by_excel_role
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill
from app.services.workflow.table_fill import TableFillWorkbookExporter, build_result_rows


class TableMappingPreviewSkill(WorkflowSkill):
    """生成候选填位预览，不实际写回 workbook。"""

    name = "table_mapping_preview"
    title = "预览填表映射"
    description = "根据计算结果预估最可能的模板填位，供人工确认和编辑。"
    input_hint = "任务描述、Excel 文档，以及上一步的表格计算结果"
    output_hint = "候选 sheet/cell 映射列表和预览说明"
    tags = ("excel", "spreadsheet", "fill", "preview")

    def __init__(self) -> None:
        self._workbook_exporter = TableFillWorkbookExporter()

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        calculator_result = context.previous_results.get("spreadsheet_calculator", {})
        result_items = calculator_result.get("results", [])
        if not result_items:
            return {
                "summary": "当前没有可用于预览填表映射的计算结果。",
                "mappingCandidates": [],
                "mappingPreview": {},
                "evidence": calculator_result.get("evidence", []),
                "evidenceRefs": calculator_result.get("evidenceRefs", calculator_result.get("evidence", [])),
            }

        rows = build_result_rows(result_items)
        target_documents = (
            filter_documents_by_excel_role(context.documents, context.previous_results, "template")
            or context.documents
        )
        preview = self._workbook_exporter.preview_fill_plan(
            task=context.task,
            documents=target_documents,
            rows=rows,
        )
        candidate_count = len(preview.get("mappingCandidates", []) or [])
        summary = str(preview.get("summary") or "").strip() or f"已生成 {candidate_count} 条候选填位。"

        return {
            "summary": summary,
            "mappingCandidates": list(preview.get("mappingCandidates", []) or []),
            "mappingPreview": preview,
            "crossCheck": dict(preview.get("crossCheck", {}) or {}),
            "evidence": calculator_result.get("evidence", []),
            "evidenceRefs": calculator_result.get("evidenceRefs", calculator_result.get("evidence", [])),
        }
