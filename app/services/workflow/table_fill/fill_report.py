"""Excel 填写报告生成工具。"""

from __future__ import annotations

import base64

from openpyxl.utils import get_column_letter


class TableFillReportBuilder:
    """把填表审计记录整理成 Markdown 报告和下载文件。"""

    def build(
        self,
        *,
        task: str,
        headers: list[str],
        rows: list[dict[str, object]],
        fill_audit: list[object],
        fill_stats: dict[str, object],
        crosscheck: dict[str, object],
        export_files: list[dict[str, object]],
    ) -> dict[str, object]:
        report_rows = self._build_report_rows(headers=headers, rows=rows, fill_audit=fill_audit)
        markdown = self._build_markdown(
            task=task,
            fill_stats=fill_stats,
            crosscheck=crosscheck,
            report_rows=report_rows,
        )
        return {
            "rows": report_rows,
            "markdown": markdown,
            "exportFile": self._build_export_file(markdown, export_files),
        }

    def _build_report_rows(
        self,
        *,
        headers: list[str],
        rows: list[dict[str, object]],
        fill_audit: list[object],
    ) -> list[dict[str, object]]:
        audit_items = [item for item in fill_audit if isinstance(item, dict)]
        report_rows = [
            self._build_report_row_from_audit(item)
            for item in audit_items
            if str(item.get("status") or "") != "result_sheet_created"
        ]

        result_sheet_audit = next(
            (
                item
                for item in audit_items
                if str(item.get("status") or "") == "result_sheet_created"
                and str(item.get("sheet") or "").strip()
            ),
            None,
        )
        if result_sheet_audit is not None:
            report_rows.extend(
                self._build_result_sheet_rows(
                    headers=headers,
                    rows=rows,
                    sheet_name=str(result_sheet_audit.get("sheet") or "").strip(),
                )
            )

        if not report_rows:
            report_rows.extend(
                self._build_unlocated_row(index=index, row=row)
                for index, row in enumerate(rows, start=1)
            )
        return report_rows

    def _build_report_row_from_audit(self, item: dict[str, object]) -> dict[str, object]:
        return {
            "mappingId": item.get("mappingId"),
            "status": item.get("status"),
            "targetSheet": item.get("sheet"),
            "targetCell": item.get("cell"),
            "metric": item.get("metric"),
            "value": item.get("value"),
            "existingValue": item.get("existingValue"),
            "sourceDocument": item.get("sourceDocument"),
            "sourceSheet": item.get("sourceSheet"),
            "sourceColumn": item.get("sourceColumn"),
            "decisionSource": item.get("decisionSource"),
            "writePolicy": item.get("writePolicy"),
            "riskLevel": item.get("riskLevel"),
            "message": item.get("message") or item.get("reasonSummary"),
        }

    def _build_result_sheet_rows(
        self,
        *,
        headers: list[str],
        rows: list[dict[str, object]],
        sheet_name: str,
    ) -> list[dict[str, object]]:
        result_column_index = headers.index("结果") + 1 if "结果" in headers else None
        report_rows: list[dict[str, object]] = []
        for row_index, row in enumerate(rows, start=2):
            target_cell = (
                f"{get_column_letter(result_column_index)}{row_index}"
                if result_column_index is not None
                else ""
            )
            report_rows.append(
                {
                    "mappingId": "",
                    "status": "result_sheet_written",
                    "targetSheet": sheet_name,
                    "targetCell": target_cell,
                    "metric": row.get("指标"),
                    "value": row.get("结果"),
                    "existingValue": None,
                    "sourceDocument": row.get("文档"),
                    "sourceSheet": row.get("工作表"),
                    "sourceColumn": row.get("数值字段"),
                    "decisionSource": "system",
                    "writePolicy": "only_empty",
                    "riskLevel": "low",
                    "message": "模板未能稳定定位时，结果写入系统生成的结果表。",
                }
            )
        return report_rows

    def _build_unlocated_row(self, *, index: int, row: dict[str, object]) -> dict[str, object]:
        return {
            "mappingId": f"row_{index}",
            "status": "not_written",
            "targetSheet": "",
            "targetCell": "",
            "metric": row.get("指标"),
            "value": row.get("结果"),
            "existingValue": None,
            "sourceDocument": row.get("文档"),
            "sourceSheet": row.get("工作表"),
            "sourceColumn": row.get("数值字段"),
            "decisionSource": "system",
            "writePolicy": "only_empty",
            "riskLevel": "unknown",
            "message": "当前结果未形成可定位的写入记录。",
        }

    def _build_markdown(
        self,
        *,
        task: str,
        fill_stats: dict[str, object],
        crosscheck: dict[str, object],
        report_rows: list[dict[str, object]],
    ) -> str:
        if not report_rows:
            return ""

        lines = [
            "# Excel 填写报告",
            "",
            "## 任务",
            self._markdown_cell(task),
            "",
            "## 填写统计",
            f"- 写入模式：{self._markdown_cell(fill_stats.get('mode'))}",
            f"- 写入单元格：{self._markdown_cell(fill_stats.get('written', 0))}",
            f"- 保留已有值：{self._markdown_cell(fill_stats.get('preservedExisting', 0))}",
            f"- 与已有值一致：{self._markdown_cell(fill_stats.get('keptExisting', 0))}",
            f"- 源数据为空：{self._markdown_cell(fill_stats.get('sourceEmpty', 0))}",
        ]
        if crosscheck:
            lines.extend(
                [
                    f"- Review 状态：{self._markdown_cell(crosscheck.get('status', 'skipped'))}",
                    f"- Review 风险：{self._markdown_cell(crosscheck.get('riskLevel', 'unknown'))}",
                    f"- Review 阻断：{self._markdown_cell(crosscheck.get('blockWrite', False))}",
                ]
            )

        lines.extend(
            [
                "",
                "## 填写记录",
                "| 序号 | 状态 | 填写位置 | 填写数据 | 指标 | 数据来源 | 决策来源 | 风险 | 说明 |",
                "| ---: | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for index, item in enumerate(report_rows, start=1):
            target = self._join_target(item.get("targetSheet"), item.get("targetCell"))
            source = self._join_source(
                item.get("sourceDocument"),
                item.get("sourceSheet"),
                item.get("sourceColumn"),
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(index),
                        self._markdown_cell(item.get("status")),
                        self._markdown_cell(target),
                        self._markdown_cell(item.get("value")),
                        self._markdown_cell(item.get("metric")),
                        self._markdown_cell(source),
                        self._markdown_cell(item.get("decisionSource")),
                        self._markdown_cell(item.get("riskLevel")),
                        self._markdown_cell(item.get("message")),
                    ]
                )
                + " |"
            )
        return "\n".join(lines)

    def _build_export_file(
        self,
        markdown: str,
        export_files: list[dict[str, object]],
    ) -> dict[str, object] | None:
        if not markdown:
            return None
        return {
            "label": "Excel 填写报告",
            "filename": self._build_filename(export_files),
            "mimeType": "text/markdown; charset=utf-8",
            "contentBase64": base64.b64encode(markdown.encode("utf-8")).decode("ascii"),
        }

    def _build_filename(self, export_files: list[dict[str, object]]) -> str:
        for item in export_files:
            filename = str(item.get("filename") or "").strip()
            if not filename:
                continue
            base_name = filename.rsplit(".", 1)[0] if "." in filename else filename
            return f"{base_name}_fill_report.md"
        return "excel_fill_report.md"

    def _join_target(self, sheet: object, cell: object) -> str:
        sheet_text = str(sheet or "").strip()
        cell_text = str(cell or "").strip()
        if sheet_text and cell_text:
            return f"{sheet_text} / {cell_text}"
        return sheet_text or cell_text or "-"

    def _join_source(self, document: object, sheet: object, column: object) -> str:
        parts = [
            str(value or "").strip()
            for value in (document, sheet, column)
            if str(value or "").strip()
        ]
        return " / ".join(parts) or "-"

    def _markdown_cell(self, value: object) -> str:
        text = str(value if value is not None else "-").replace("\n", " ").replace("\r", " ").strip()
        return text.replace("|", "\\|") or "-"
