"""填表技能。

这个技能位于 `spreadsheet_calculator` 之后。
它本身不负责计算，而是负责：

1. 从 `previous_results` 读取表格计算结果
2. 把结果整理成统一的结果行
3. 生成聊天区可展示的 Markdown 预览
4. 调用 workbook 导出器生成可下载的 Excel
5. 调用报告生成器记录写入位置、数据和来源

这样技能层只做编排，真正的结果整理和 workbook 写入逻辑会分别落在独立模块里。
"""

from __future__ import annotations

from app.services.workflow.excel_roles import filter_documents_by_excel_role
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill
from app.services.workflow.table_fill import (
    TableFillReportBuilder,
    TableFillWorkbookExporter,
    build_markdown_table,
    build_result_rows,
    resolve_present_headers,
)


class TableFillerSkill(WorkflowSkill):
    """把表格计算结果整理成用户可确认的表格输出。"""

    name = "table_filler"
    title = "按要求填表"
    description = "把表格计算结果整理成可确认、可回填的结构化结果表。"
    input_hint = "任务描述，以及前一步的表格计算结果"
    output_hint = "结构化表格行、Markdown 结果表和可下载 Excel"
    requires_approval = True
    tags = ("excel", "spreadsheet", "fill")

    def __init__(self) -> None:
        self._workbook_exporter = TableFillWorkbookExporter()
        self._fill_report_builder = TableFillReportBuilder()

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        """执行填表步骤。

        依赖关系：
        - `spreadsheet_calculator` 需要先执行，并把结果放进 `context.previous_results`

        输出内容：
        - `rows`：统一结构的结果行
        - `filledTableMarkdown`：给前端预览使用的 Markdown
        - `exportFiles`：可下载的 Excel 文件和填写报告
        - `evidence`：沿用计算步骤产出的证据
        """
        calculator_result = context.previous_results.get("spreadsheet_calculator", {})
        result_items = calculator_result.get("results", [])

        if not result_items:
            # 即使没有可填结果，也保持返回结构稳定，避免前端到处判断字段是否存在。
            return {
                "summary": "当前没有可用于填表的计算结果。",
                "headers": [],
                "rows": [],
                "filledTableMarkdown": build_markdown_table([], []),
                "fillReportMarkdown": "",
                "fillReportRows": [],
                "exportFiles": [],
                "fillAudit": [],
                "fillStats": {
                    "mode": "none",
                    "written": 0,
                    "keptExisting": 0,
                    "preservedExisting": 0,
                    "sourceEmpty": 0,
                },
                "evidence": calculator_result.get("evidence", []),
                "evidenceRefs": calculator_result.get("evidenceRefs", calculator_result.get("evidence", [])),
            }

        # 先统一整理结果行，再复用这份结构生成 Markdown 和导出文件。
        rows = build_result_rows(result_items)
        headers = resolve_present_headers(rows)
        markdown = build_markdown_table(headers, rows)
        manual_mappings = self._resolve_manual_mappings(context.inputs)
        if bool(context.inputs.get("requireConfirmedCandidates")):
            self._require_confirmation_for_low_confidence_candidates(
                preview_result=context.previous_results.get("table_mapping_preview", {}),
                manual_mappings=manual_mappings,
            )
        target_documents = (
            filter_documents_by_excel_role(context.documents, context.previous_results, "template")
            or context.documents
        )
        export_bundle = self._workbook_exporter.build_export_bundle(
            task=context.task,
            documents=target_documents,
            headers=headers,
            rows=rows,
            manual_mappings=manual_mappings,
            crosscheck_result=(
                None if manual_mappings else self._resolve_preview_crosscheck(context.previous_results)
            ),
        )
        export_files = list(export_bundle.get("exportFiles", []))
        fill_audit = list(export_bundle.get("fillAudit", []))
        fill_stats = dict(export_bundle.get("fillStats", {}))
        crosscheck = dict(export_bundle.get("crossCheck", {}))
        fill_report = self._fill_report_builder.build(
            task=context.task,
            headers=headers,
            rows=rows,
            fill_audit=fill_audit,
            fill_stats=fill_stats,
            crosscheck=crosscheck,
            export_files=export_files,
        )
        fill_report_rows = list(fill_report.get("rows", []))
        fill_report_markdown = str(fill_report.get("markdown") or "")
        fill_report_export_file = fill_report.get("exportFile")
        if isinstance(fill_report_export_file, dict):
            export_files.append(fill_report_export_file)

        summary = f"已根据任务整理出 {len(rows)} 行结果表，可继续人工确认或回填。"
        if export_files:
            summary += " 同时生成了可下载的 Excel 回填结果和填写报告。"
        written_count = int(fill_stats.get("written", 0) or 0)
        preserved_count = int(fill_stats.get("preservedExisting", 0) or 0)
        skipped_count = int(fill_stats.get("skippedManual", 0) or 0)
        if written_count:
            summary += f" 已写入 {written_count} 个模板单元格。"
        if preserved_count:
            summary += f" 有 {preserved_count} 个已有值被保留，避免覆盖。"
        manual_count = self._count_written_audit_by_decision(fill_audit, "manual")
        auto_count = self._count_written_audit_by_decision(fill_audit, "auto")
        if auto_count or manual_count or skipped_count:
            summary += f" 自动命中 {auto_count} 项，人工确认 {manual_count} 项，跳过 {skipped_count} 项。"
        if crosscheck:
            if crosscheck.get("blockWrite"):
                summary += " Review 交叉检查判定风险较高，已阻止自动回填。"
            elif crosscheck.get("enabled"):
                summary += f" Review 交叉检查完成，风险等级为 {crosscheck.get('riskLevel', 'unknown')}。"

        return {
            "summary": summary,
            "headers": headers,
            "rows": rows,
            "filledTableMarkdown": markdown,
            "fillReportMarkdown": fill_report_markdown,
            "fillReportRows": fill_report_rows,
            "exportFiles": export_files,
            "fillAudit": fill_audit,
            "fillStats": fill_stats,
            "crossCheck": crosscheck,
            "evidence": calculator_result.get("evidence", []),
            "evidenceRefs": calculator_result.get("evidenceRefs", calculator_result.get("evidence", [])),
        }

    def _resolve_manual_mappings(self, inputs: dict[str, object]) -> list[dict[str, object]]:
        """读取人工确认阶段提交的手工映射。"""
        manual_mappings = inputs.get("manualMappings", [])
        if not isinstance(manual_mappings, list):
            return []
        return [item for item in manual_mappings if isinstance(item, dict)]

    def _count_written_audit_by_decision(
        self,
        fill_audit: list[object],
        decision_source: str,
    ) -> int:
        return sum(
            1
            for item in fill_audit
            if isinstance(item, dict)
            and str(item.get("decisionSource") or "") == decision_source
            and str(item.get("status") or "") == "written"
        )

    def _resolve_preview_crosscheck(
        self,
        previous_results: dict[str, dict[str, object]],
    ) -> dict[str, object] | None:
        preview_result = previous_results.get("table_mapping_preview", {})
        crosscheck = preview_result.get("crossCheck") if isinstance(preview_result, dict) else None
        return crosscheck if isinstance(crosscheck, dict) and crosscheck else None

    def _require_confirmation_for_low_confidence_candidates(
        self,
        *,
        preview_result: dict[str, object],
        manual_mappings: list[dict[str, object]],
    ) -> None:
        candidates = preview_result.get("mappingCandidates", [])
        if not isinstance(candidates, list) or not candidates:
            return

        confirmed_mapping_ids = {
            str(item.get("mappingId") or "").strip()
            for item in manual_mappings
            if str(item.get("mappingId") or "").strip()
        }
        blocking_candidates = [
            item
            for item in candidates
            if isinstance(item, dict)
            and bool(item.get("requiresConfirmation"))
            and str(item.get("mappingId") or "").strip() not in confirmed_mapping_ids
        ]
        if blocking_candidates:
            metrics = "、".join(
                str(item.get("metric") or item.get("mappingId") or "").strip()
                for item in blocking_candidates[:3]
                if str(item.get("metric") or item.get("mappingId") or "").strip()
            )
            detail = f"：{metrics}" if metrics else ""
            raise ValueError(f"存在低置信度填位尚未逐项确认{detail}。请先在人工确认面板确认或跳过这些结果。")
