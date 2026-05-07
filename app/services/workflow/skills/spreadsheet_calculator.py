"""表格计算技能。

读取 Excel 结构化数据后，根据任务语义执行基础统计、跨 sheet 汇总和常见趋势指标计算。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.workflow.evidence import build_manual_evidence
from app.services.workflow.excel_roles import filter_documents_by_excel_role
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill

CALCULATION_OPERATION_KEYWORDS = {
    "sum": ("sum", "total", "合计", "求和", "汇总"),
    "avg": ("avg", "average", "mean", "平均"),
    "max": ("max", "maximum", "最大", "最高"),
    "min": ("min", "minimum", "最小", "最低"),
    "count": ("count", "数量", "条数", "行数", "多少"),
    "ratio": ("ratio", "占比", "比例"),
    "intensity": ("intensity", "强度", "密度"),
    "yoy": ("同比", "year over year", "yoy"),
    "mom": ("环比", "month over month", "mom"),
}
CALCULATION_BUILDERS = {
    "sum": sum,
    "avg": lambda values: sum(values) / len(values),
    "max": max,
    "min": min,
    "count": len,
}
HEADER_ALIASES = {
    "scope 1": ("scope 1", "范围一", "范围1"),
    "scope 2": ("scope 2", "范围二", "范围2"),
    "scope 3": ("scope 3", "范围三", "范围3"),
    "amount": ("金额", "amount", "费用", "cost", "支出"),
    "month": ("月份", "month", "期间"),
    "year": ("年份", "year", "年度"),
    "revenue": ("收入", "revenue", "营收"),
    "production": ("产量", "production", "output"),
    "employee": ("员工", "人数", "headcount"),
}
TEMPLATE_DOCUMENT_HINTS = ("template", "summary", "result", "report", "form", "blank", "模板", "汇总", "填报", "填表", "回填", "结果", "空白")
SOURCE_DOCUMENT_HINTS = ("detail", "data", "source", "ledger", "raw", "明细", "台账", "原始", "数据")
TEMPLATE_SHEET_HINTS = ("summary", "result", "report", "form", "汇总", "模板", "填报", "结果")


class SpreadsheetCalculatorSkill(WorkflowSkill):
    """对 Excel 数值列执行基础统计计算。"""

    name = "spreadsheet_calculator"
    title = "表格计算"
    description = "读取 Excel 的结构化行列数据，并按任务要求做求和、平均值、最大最小值、趋势和比率计算。"
    input_hint = "包含 structuredData 的 Excel 文档和任务描述"
    output_hint = "按工作表、列名和可选分组字段计算出的数值结果"
    tags = ("excel", "spreadsheet", "calculate")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        tables = self._collect_tables(context)
        if not tables:
            return {
                "summary": "当前没有可用于计算的结构化 Excel 数据。",
                "results": [],
                "operations": [],
            }

        task_lower = context.task.lower()
        operations = self._detect_operations(task_lower)
        time_tokens = self._extract_time_tokens(task_lower)
        results: list[dict[str, object]] = []
        evidence_items: list[dict[str, str]] = []
        planned_calculations = self._resolve_planned_calculations(context.previous_results)

        if planned_calculations:
            operations = list(dict.fromkeys(str(item.get("operation") or "") for item in planned_calculations if str(item.get("operation") or "")))
            results, evidence_items = self._execute_planned_calculations(
                tables=tables,
                calculations=planned_calculations,
            )
            cross_sheet_results = self._build_cross_sheet_results(task_lower, tables, operations, time_tokens)
            results.extend(cross_sheet_results)
            for item in cross_sheet_results:
                evidence_items.append(
                    build_manual_evidence(
                        title=f"{item['column']} 跨表汇总",
                        document_id=str(item.get("documentId") or ""),
                        document_name=str(item["document"]),
                        location=f"工作表 {', '.join(item.get('sourceSheets', []))}",
                        excerpt=f"跨工作表汇总得到 {item['column']} 指标。",
                        source_step=self.title,
                    )
                )
        else:
            for table in tables:
                numeric_columns = list(table["numericColumns"])
                if not numeric_columns:
                    continue

                headers = list(table["headers"])
                target_columns = self._match_headers(task_lower, numeric_columns) or numeric_columns
                group_by = self._match_group_by(task_lower, headers, numeric_columns)
                filtered_rows = self._filter_rows_by_time(table["rows"], time_tokens)
                if not filtered_rows:
                    filtered_rows = list(table["rows"])

                for column in target_columns:
                    values = self._collect_numeric_values(filtered_rows, column)
                    if not values:
                        continue

                    result_item = self._build_result_item(
                        table=table,
                        rows=filtered_rows,
                        column=column,
                        operations=operations,
                        group_by=group_by,
                        time_tokens=time_tokens,
                    )
                    if result_item is None:
                        continue
                    results.append(result_item)
                    evidence_items.append(
                        self._build_calculation_evidence(
                            table=table,
                            column=column,
                            values=values,
                            result_item=result_item,
                        )
                    )

            cross_sheet_results = self._build_cross_sheet_results(task_lower, tables, operations, time_tokens)
            results.extend(cross_sheet_results)
            for item in cross_sheet_results:
                evidence_items.append(
                    build_manual_evidence(
                        title=f"{item['column']} 跨表汇总",
                        document_id=str(item.get("documentId") or ""),
                        document_name=str(item["document"]),
                        location=f"工作表 {', '.join(item.get('sourceSheets', []))}",
                        excerpt=f"跨工作表汇总得到 {item['column']} 指标。",
                        source_step=self.title,
                    )
                )

        if not results:
            return {
                "summary": "Excel 已读取，但没有识别到可计算的数值列。",
                "results": [],
                "operations": operations,
            }

        summary_lines = [self._build_result_line(result) for result in results[:8]]
        if len(results) > 8:
            summary_lines.append(f"其余 {len(results) - 8} 条计算结果已保留在结构化输出中。")

        return {
            "summary": f"已完成 {len(results)} 个表格计算项。\n" + "\n".join(summary_lines),
            "results": results,
            "operations": operations,
            "evidence": evidence_items[:8],
            "evidenceRefs": evidence_items[:8],
        }

    def _resolve_planned_calculations(
        self,
        previous_results: dict[str, dict[str, Any]],
    ) -> list[dict[str, object]]:
        planner_result = previous_results.get("calculation_planner", {})
        calculations = planner_result.get("calculations") or (planner_result.get("calculationPlan") or {}).get("calculations")
        if not isinstance(calculations, list):
            return []
        return [item for item in calculations if isinstance(item, dict)]

    def _execute_planned_calculations(
        self,
        *,
        tables: list[dict[str, object]],
        calculations: list[dict[str, object]],
    ) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
        results: list[dict[str, object]] = []
        evidence_items: list[dict[str, str]] = []

        for calculation in calculations:
            table = self._find_table_for_calculation(tables, calculation)
            if table is None:
                continue

            column = str(calculation.get("column") or "").strip()
            if column not in table.get("numericColumns", []):
                continue

            operation = str(calculation.get("operation") or "").strip()
            operations = [operation] if operation else []
            filters = calculation.get("filters", {})
            time_tokens = list(filters.get("timeTokens", []) if isinstance(filters, dict) else [])
            filtered_rows = self._filter_rows_by_time(table["rows"], time_tokens)
            if not filtered_rows:
                filtered_rows = list(table["rows"])

            values = self._collect_numeric_values(filtered_rows, column)
            if not values:
                continue

            result_item = self._build_result_item(
                table=table,
                rows=filtered_rows,
                column=column,
                operations=operations,
                group_by=str(calculation.get("groupBy") or "").strip() or None,
                time_tokens=time_tokens,
            )
            if result_item is None:
                continue
            result_item["calculationId"] = calculation.get("calculationId")
            result_item["label"] = calculation.get("label")
            results.append(result_item)
            evidence_items.append(
                self._build_calculation_evidence(
                    table=table,
                    column=column,
                    values=values,
                    result_item=result_item,
                )
            )

        return results, evidence_items

    def _find_table_for_calculation(
        self,
        tables: list[dict[str, object]],
        calculation: dict[str, object],
    ) -> dict[str, object] | None:
        source_document_id = str(calculation.get("sourceDocumentId") or "").strip()
        source_workbook = str(calculation.get("sourceWorkbook") or "").strip()
        source_sheet = str(calculation.get("sourceSheet") or "").strip()

        for table in tables:
            if source_document_id and str(table.get("documentId") or "").strip() != source_document_id:
                continue
            if source_workbook and str(table.get("document") or "").strip() != source_workbook:
                continue
            if source_sheet and str(table.get("sheet") or "").strip() != source_sheet:
                continue
            return table
        return None

    def _build_result_item(
        self,
        *,
        table: dict[str, object],
        rows: list[dict[str, object]],
        column: str,
        operations: list[str],
        group_by: str | None,
        time_tokens: list[str],
    ) -> dict[str, object] | None:
        values = self._collect_numeric_values(rows, column)
        if not values:
            return None

        headers = list(table["headers"])
        numeric_columns = list(table["numericColumns"])
        result_item: dict[str, object] = {
            "documentId": table.get("documentId"),
            "document": table["document"],
            "sheet": table["sheet"],
            "column": column,
            "metrics": self._build_metrics(values, operations),
            "filters": {"timeTokens": time_tokens},
            "rowRange": self._resolve_row_range(rows),
        }

        grouped_metrics = self._build_grouped_metrics(
            rows,
            column,
            group_by,
            operations,
        )
        if grouped_metrics:
            result_item["groupBy"] = group_by
            result_item["groupedMetrics"] = grouped_metrics

        special_metrics = self._build_special_metrics(
            rows=rows,
            headers=headers,
            numeric_columns=numeric_columns,
            target_column=column,
            operations=operations,
        )
        if special_metrics:
            result_item["metrics"].update(special_metrics)

        if not result_item["metrics"] and not result_item.get("groupedMetrics"):
            return None
        return result_item

    def _build_calculation_evidence(
        self,
        *,
        table: dict[str, object],
        column: str,
        values: list[float],
        result_item: dict[str, object],
    ) -> dict[str, str]:
        return build_manual_evidence(
            title=f"{column} 计算结果",
            document_id=str(table.get("documentId") or ""),
            document_name=str(table["document"]),
            location=f"工作表 {table['sheet']} / 数值列 {column}",
            excerpt=f"基于 {len(values)} 行可计算数据，执行 {', '.join(sorted(result_item['metrics']))}。",
            source_step=self.title,
            sheet=str(table["sheet"]),
            row_start=result_item["rowRange"]["rowStart"],
            row_end=result_item["rowRange"]["rowEnd"],
        )

    def _collect_tables(self, context: SkillExecutionContext) -> list[dict[str, object]]:
        source_documents = self._select_source_documents(context)
        return [
            {
                "documentId": document.documentId,
                "document": document.name,
                "sheet": str(sheet.get("title", "Sheet")),
                "headers": list(sheet.get("headers", [])),
                "rows": list(sheet.get("rows", [])),
                "numericColumns": list(sheet.get("numericColumns", [])),
            }
            for document in source_documents
            for sheet in document.structuredData.get("sheets", [])
        ]

    def _select_source_documents(self, context: SkillExecutionContext) -> list[Any]:
        """尽量排除回填模板，只保留更像源数据的工作簿参与计算。"""
        role_documents = filter_documents_by_excel_role(
            context.documents,
            context.previous_results,
            "source",
        )
        if role_documents:
            return role_documents

        documents = context.resolve_documents(allowed_types={"excel"})
        if len(documents) <= 1:
            return documents

        task_lower = context.task.lower()
        mentioned_documents = [
            document for document in documents
            if self._document_is_mentioned(task_lower, str(getattr(document, "name", "") or ""))
        ]
        candidate_documents = mentioned_documents or documents
        scored_documents = [
            (
                self._score_source_document(task_lower, document),
                self._score_template_document(task_lower, document),
                document,
            )
            for document in candidate_documents
        ]

        preferred_documents = [
            document
            for source_score, template_score, document in scored_documents
            if source_score > template_score
        ]
        if preferred_documents:
            return preferred_documents

        if len(candidate_documents) == 1:
            return candidate_documents

        non_template_documents = [
            document
            for source_score, template_score, document in scored_documents
            if template_score == 0 or source_score >= template_score
        ]
        return non_template_documents or candidate_documents

    def _document_is_mentioned(self, task_lower: str, document_name: str) -> bool:
        lowered_name = str(document_name or "").strip().lower()
        if not lowered_name:
            return False
        stem = lowered_name.rsplit(".", 1)[0] if "." in lowered_name else lowered_name
        return lowered_name in task_lower or (stem and stem in task_lower)

    def _score_source_document(self, task_lower: str, document: Any) -> int:
        name = str(getattr(document, "name", "") or "").strip().lower()
        score = 0

        if self._document_is_mentioned(task_lower, name):
            score += 5
        score += 4 * sum(1 for hint in SOURCE_DOCUMENT_HINTS if hint in name)

        for sheet in document.structuredData.get("sheets", []):
            if not isinstance(sheet, dict):
                continue
            row_count = int(sheet.get("rowCount", 0) or 0)
            numeric_columns = [str(column) for column in sheet.get("numericColumns", []) if str(column).strip()]
            headers = [str(header) for header in sheet.get("headers", []) if str(header).strip()]
            task_header_hit = any(self._header_matches_task(header, task_lower) for header in [*headers, *numeric_columns])

            if row_count and numeric_columns:
                score += 4 if row_count >= 5 else 2
            if row_count >= 5:
                score += 1
            if len(headers) >= 2:
                score += 1
            if task_header_hit:
                score += 2

        return score

    def _score_template_document(self, task_lower: str, document: Any) -> int:
        name = str(getattr(document, "name", "") or "").strip().lower()
        score = 3 * sum(1 for hint in TEMPLATE_DOCUMENT_HINTS if hint in name)

        for sheet in document.structuredData.get("sheets", []):
            if not isinstance(sheet, dict):
                continue
            title = str(sheet.get("title", "") or "").lower()
            headers = [str(header) for header in sheet.get("headers", []) if str(header).strip()]
            row_count = int(sheet.get("rowCount", 0) or 0)
            numeric_columns = [str(column) for column in sheet.get("numericColumns", []) if str(column).strip()]
            task_header_hit = any(self._header_matches_task(header, task_lower) for header in [*headers, *numeric_columns])

            if any(hint in title for hint in TEMPLATE_SHEET_HINTS):
                score += 2
            if any(self._matches_template_header(header, "指标") for header in headers) and any(
                self._matches_template_header(header, "结果") for header in headers
            ):
                score += 4
            if row_count <= 3 and len(numeric_columns) <= 1:
                score += 1 if task_header_hit else 3

        return score

    def _matches_template_header(self, header: str, canonical: str) -> bool:
        normalized = str(header or "").strip().lower()
        aliases = {canonical.lower(), *(alias.lower() for alias in (HEADER_ALIASES.get(canonical.lower()) or ()))} if canonical.lower() in HEADER_ALIASES else {canonical.lower()}
        if canonical == "指标":
            aliases = {"指标", "metric", "metrics"}
        if canonical == "结果":
            aliases = {"结果", "result", "value", "数值"}
        return normalized in aliases

    def _detect_operations(self, task_lower: str) -> list[str]:
        detected = [
            operation
            for operation, keywords in CALCULATION_OPERATION_KEYWORDS.items()
            if any(keyword in task_lower for keyword in keywords)
        ]
        return detected or ["sum", "count"]

    def _match_headers(self, task_lower: str, headers: list[str]) -> list[str]:
        matched: list[str] = []
        for header in headers:
            if self._header_matches_task(header, task_lower):
                matched.append(header)
        return matched

    def _header_matches_task(self, header: str, task_lower: str) -> bool:
        normalized = self._normalize_header(header)
        header_text = str(header).strip().lower()
        if header_text and header_text in task_lower:
            return True
        for alias_key, aliases in HEADER_ALIASES.items():
            if normalized != alias_key:
                continue
            if any(alias.lower() in task_lower for alias in aliases):
                return True
        return False

    def _match_group_by(
        self,
        task_lower: str,
        headers: list[str],
        numeric_columns: list[str],
    ) -> str | None:
        dimension_headers = [header for header in headers if header not in numeric_columns]
        return next(iter(self._match_headers(task_lower, dimension_headers)), None)

    def _extract_time_tokens(self, task_lower: str) -> list[str]:
        tokens = []
        for token in (
            "1月", "2月", "3月", "4月", "5月", "6月",
            "7月", "8月", "9月", "10月", "11月", "12月",
            "q1", "q2", "q3", "q4", "一季度", "二季度", "三季度", "四季度",
            "2024", "2025", "2026",
        ):
            if token in task_lower:
                tokens.append(token)
        return tokens

    def _filter_rows_by_time(
        self,
        rows: list[dict[str, object]],
        time_tokens: list[str],
    ) -> list[dict[str, object]]:
        if not time_tokens:
            return list(rows)
        filtered = []
        for row in rows:
            haystack = " ".join(str(value or "").lower() for value in row.values())
            if any(token.lower() in haystack for token in time_tokens):
                filtered.append(row)
        return filtered

    def _collect_numeric_values(
        self,
        rows: list[dict[str, object]],
        column: str,
    ) -> list[float]:
        return [
            numeric_value
            for row in rows
            if (numeric_value := self._parse_numeric(row.get(column))) is not None
        ]

    def _build_grouped_metrics(
        self,
        rows: list[dict[str, object]],
        column: str,
        group_by: str | None,
        operations: list[str],
    ) -> list[dict[str, object]]:
        if not group_by:
            return []

        grouped_values: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            numeric_value = self._parse_numeric(row.get(column))
            if numeric_value is None:
                continue
            group_value = row.get(group_by)
            grouped_values[str(group_value if group_value not in (None, "") else "空值")].append(numeric_value)

        return [
            {
                "group": group_name,
                "metrics": self._build_metrics(grouped_numbers, operations),
            }
            for group_name, grouped_numbers in grouped_values.items()
        ]

    def _build_metrics(self, values: list[float], operations: list[str]) -> dict[str, float | int]:
        metrics: dict[str, float | int] = {}

        for operation in operations:
            builder = CALCULATION_BUILDERS.get(operation)
            if builder is None:
                continue
            result = builder(values)
            metrics[operation] = result if operation == "count" else self._normalize_number(result)

        return metrics

    def _build_special_metrics(
        self,
        *,
        rows: list[dict[str, object]],
        headers: list[str],
        numeric_columns: list[str],
        target_column: str,
        operations: list[str],
    ) -> dict[str, float | int]:
        metrics: dict[str, float | int] = {}
        values = self._collect_numeric_values(rows, target_column)
        if not values:
            return metrics

        if "ratio" in operations and len(numeric_columns) > 1:
            total = sum(
                sum(self._collect_numeric_values(rows, column))
                for column in numeric_columns
            )
            if total:
                metrics["ratio"] = self._normalize_number(sum(values) / total)

        if "intensity" in operations:
            denominator = self._infer_intensity_denominator(rows, headers, target_column)
            if denominator:
                metrics["intensity"] = self._normalize_number(sum(values) / denominator)

        trend_series = self._build_trend_series(rows, headers, target_column)
        if trend_series:
            if "yoy" in operations and len(trend_series) >= 2 and trend_series[-2] != 0:
                metrics["yoy"] = self._normalize_number((trend_series[-1] - trend_series[-2]) / abs(trend_series[-2]))
            if "mom" in operations and len(trend_series) >= 2 and trend_series[-2] != 0:
                metrics["mom"] = self._normalize_number((trend_series[-1] - trend_series[-2]) / abs(trend_series[-2]))

        return metrics

    def _build_cross_sheet_results(
        self,
        task_lower: str,
        tables: list[dict[str, object]],
        operations: list[str],
        time_tokens: list[str],
    ) -> list[dict[str, object]]:
        if not any(keyword in task_lower for keyword in ("跨sheet", "跨工作表", "所有工作表", "全部工作表", "合并")):
            return []

        buckets: dict[tuple[str, str], dict[str, Any]] = {}
        document_totals: dict[str, float] = defaultdict(float)
        for table in tables:
            filtered_rows = self._filter_rows_by_time(table["rows"], time_tokens) or list(table["rows"])
            for column in table["numericColumns"]:
                column_values = self._collect_numeric_values(filtered_rows, column)
                bucket = buckets.setdefault(
                    (str(table["document"]), str(column)),
                    {
                        "documentId": table.get("documentId"),
                        "document": table["document"],
                        "column": column,
                        "values": [],
                        "sourceSheets": [],
                    },
                )
                bucket["values"].extend(column_values)
                bucket["sourceSheets"].append(str(table["sheet"]))
                document_totals[str(table["document"])] += sum(column_values)

        results = []
        for bucket in buckets.values():
            if not bucket["values"]:
                continue
            metrics = self._build_metrics(bucket["values"], operations)
            if "ratio" in operations and document_totals.get(str(bucket["document"])):
                metrics["ratio"] = self._normalize_number(
                    sum(bucket["values"]) / document_totals[str(bucket["document"])]
                )
            results.append(
                {
                    "documentId": bucket["documentId"],
                    "document": bucket["document"],
                    "sheet": "跨工作表",
                    "column": bucket["column"],
                    "metrics": metrics,
                    "sourceSheets": sorted(dict.fromkeys(bucket["sourceSheets"])),
                    "filters": {"timeTokens": time_tokens},
                    "rowRange": {"rowStart": None, "rowEnd": None},
                }
            )
        return results

    def _infer_intensity_denominator(
        self,
        rows: list[dict[str, object]],
        headers: list[str],
        target_column: str,
    ) -> float | None:
        candidate_headers = [
            header
            for header in headers
            if header != target_column and self._normalize_header(header) in {"production", "employee", "revenue"}
        ]
        for header in candidate_headers:
            values = self._collect_numeric_values(rows, header)
            if values and sum(values) != 0:
                return sum(values)
        return None

    def _build_trend_series(
        self,
        rows: list[dict[str, object]],
        headers: list[str],
        target_column: str,
    ) -> list[float]:
        dimension_headers = [header for header in headers if header != target_column]
        time_header = next(
            (
                header
                for header in dimension_headers
                if self._normalize_header(header) in {"month", "year"}
            ),
            None,
        )
        if time_header is None:
            return []

        series = []
        for row in rows:
            if row.get(time_header) in (None, ""):
                continue
            value = self._parse_numeric(row.get(target_column))
            if value is None:
                continue
            series.append(value)
        return series

    def _resolve_row_range(self, rows: list[dict[str, object]]) -> dict[str, int | None]:
        if not rows:
            return {"rowStart": None, "rowEnd": None}
        return {"rowStart": 1, "rowEnd": len(rows)}

    def _normalize_header(self, header: str) -> str:
        lowered = str(header or "").strip().lower()
        for alias_key, aliases in HEADER_ALIASES.items():
            if lowered == alias_key or any(alias.lower() == lowered for alias in aliases):
                return alias_key
        return lowered

    def _parse_numeric(self, value: object) -> float | None:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip().replace(",", "")
        if not text:
            return None
        if text.endswith("%"):
            try:
                return float(text[:-1]) / 100
            except ValueError:
                return None

        cleaned = text.replace("¥", "").replace("$", "").replace("￥", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _normalize_number(self, value: float) -> float | int:
        rounded = round(value, 4)
        return int(rounded) if rounded.is_integer() else rounded

    def _build_result_line(self, result: dict[str, object]) -> str:
        metrics = result.get("metrics", {})
        metric_text = "，".join(f"{name}={value}" for name, value in metrics.items()) or "无结果"
        if result.get("sourceSheets"):
            return (
                f"- {result['document']} / 跨工作表 / {result['column']}："
                f"{metric_text}；来源 {', '.join(result['sourceSheets'])}。"
            )
        if result.get("groupBy"):
            group_count = len(result.get("groupedMetrics", []))
            return (
                f"- {result['document']} / {result['sheet']} / {result['column']}："
                f"{metric_text}；按 {result['groupBy']} 分组 {group_count} 组。"
            )

        return f"- {result['document']} / {result['sheet']} / {result['column']}：{metric_text}"
