"""Excel 源表到目标表直填技能。"""

from __future__ import annotations

from app.services.workflow.excel_roles import filter_documents_by_excel_role
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill
from app.services.workflow.table_fill import TableDataTransferExporter


class TableDataTransferSkill(WorkflowSkill):
    """把一个源数据 workbook 的明细行自动写入目标 workbook。"""

    name = "table_data_transfer"
    title = "源表写入目标表"
    description = "按目标表表头自动匹配源表列，把源表明细数据写入目标 Excel。"
    input_hint = "源数据 Excel、目标 Excel 和任务描述"
    output_hint = "已写入的目标 Excel、列映射和逐单元格审计"
    tags = ("excel", "spreadsheet", "fill", "transfer")

    def __init__(self) -> None:
        self._exporter = TableDataTransferExporter()

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        source_documents = (
            filter_documents_by_excel_role(context.documents, context.previous_results, "source")
            or self._fallback_source_documents(context.documents)
        )
        target_documents = (
            filter_documents_by_excel_role(context.documents, context.previous_results, "template")
            or self._fallback_target_documents(context.documents, source_documents)
        )
        export_bundle = self._exporter.build_export_bundle(
            task=context.task,
            source_documents=source_documents,
            target_documents=target_documents,
        )
        stats = dict(export_bundle.get("transferStats", {}))
        written_count = int(stats.get("written", 0) or 0)
        rows_transferred = int(stats.get("rowsTransferred", 0) or 0)
        summary = str(export_bundle.get("summary") or "").strip()
        if not summary:
            summary = f"已完成源表到目标表的数据写入，写入 {rows_transferred} 行、{written_count} 个单元格。"

        return {
            **export_bundle,
            "summary": summary,
            "source": "local_skill",
        }

    def _fallback_source_documents(self, documents: list[object]) -> list[object]:
        excel_documents = [document for document in documents if getattr(document, "type", None) == "excel"]
        return excel_documents[:1]

    def _fallback_target_documents(self, documents: list[object], source_documents: list[object]) -> list[object]:
        excel_documents = [document for document in documents if getattr(document, "type", None) == "excel"]
        source_ids = {
            str(getattr(document, "documentId", "") or "").strip()
            for document in source_documents
        }
        non_source_documents = [
            document
            for document in excel_documents
            if str(getattr(document, "documentId", "") or "").strip() not in source_ids
        ]
        return non_source_documents[:1] or excel_documents[:1]
