"""Excel workflow role helpers.

Excel 填表链路里通常同时存在源数据 workbook 和模板 workbook。
这里提供确定性的角色识别与结果复用工具，供多个 skill 共享。
"""

from __future__ import annotations

from typing import Any

TEMPLATE_DOCUMENT_HINTS = (
    "template",
    "summary",
    "result",
    "report",
    "form",
    "blank",
    "模板",
    "汇总",
    "填报",
    "填表",
    "回填",
    "结果",
    "空白",
    "目标",
    "目标表",
    "目标表格",
)
SOURCE_DOCUMENT_HINTS = (
    "detail",
    "data",
    "source",
    "ledger",
    "raw",
    "明细",
    "台账",
    "原始",
    "数据",
    "数据源",
    "源表",
)
TEMPLATE_SHEET_HINTS = ("summary", "result", "report", "form", "汇总", "模板", "填报", "结果")
SOURCE_SHEET_HINTS = ("detail", "data", "ledger", "raw", "明细", "台账", "原始", "数据")


def classify_excel_documents(task: str, documents: list[Any]) -> dict[str, object]:
    """识别 Excel 文档在填表链路中的角色。"""
    excel_documents = [document for document in documents if getattr(document, "type", None) == "excel"]
    role_items = [
        _build_role_item(document=document, task=task)
        for document in excel_documents
    ]

    if not role_items:
        return {
            "summary": "当前没有可识别角色的 Excel 文档。",
            "roles": [],
            "sourceDocuments": [],
            "templateDocuments": [],
            "sourceDocumentIds": [],
            "templateDocumentIds": [],
            "warnings": ["未上传 Excel 文档。"],
        }

    source_document_ids = _select_role_document_ids(role_items, role="source")
    template_document_ids = _select_role_document_ids(role_items, role="template")
    if len(role_items) == 1:
        source_document_ids = [str(role_items[0]["documentId"])]
        template_document_ids = [str(role_items[0]["documentId"])]

    for item in role_items:
        document_id = str(item["documentId"])
        item["isSource"] = document_id in source_document_ids
        item["isTemplate"] = document_id in template_document_ids
        if item["isSource"] and item["isTemplate"]:
            item["role"] = "source_and_template"
        elif item["isTemplate"]:
            item["role"] = "template"
        elif item["isSource"]:
            item["role"] = "source"
        else:
            item["role"] = "unselected"

    source_documents = _summarize_selected_documents(role_items, source_document_ids)
    template_documents = _summarize_selected_documents(role_items, template_document_ids)
    warnings = _build_role_warnings(role_items, source_documents, template_documents)

    summary = (
        "已识别 Excel 角色："
        f"源数据 {', '.join(item['name'] for item in source_documents) or '未确定'}；"
        f"待填模板 {', '.join(item['name'] for item in template_documents) or '未确定'}。"
    )
    if warnings:
        summary += " " + "；".join(warnings)

    return {
        "summary": summary,
        "roles": role_items,
        "sourceDocuments": source_documents,
        "templateDocuments": template_documents,
        "sourceDocumentIds": source_document_ids,
        "templateDocumentIds": template_document_ids,
        "warnings": warnings,
    }


def filter_documents_by_excel_role(
    documents: list[Any],
    previous_results: dict[str, dict[str, Any]],
    role: str,
) -> list[Any]:
    """根据 `excel_role_classifier` 的结果筛选源数据或模板文档。"""
    role_result = previous_results.get("excel_role_classifier", {})
    id_key = "sourceDocumentIds" if role == "source" else "templateDocumentIds"
    document_ids = {
        str(item or "").strip()
        for item in role_result.get(id_key, []) or []
        if str(item or "").strip()
    }
    if not document_ids:
        return []

    return [
        document
        for document in documents
        if getattr(document, "type", None) == "excel"
        and str(getattr(document, "documentId", "") or "").strip() in document_ids
    ]


def _build_role_item(document: Any, task: str) -> dict[str, object]:
    source_score, source_reasons = _score_source_document(document=document, task=task)
    template_score, template_reasons = _score_template_document(document=document, task=task)
    name = str(getattr(document, "name", "") or "")
    mentioned = _document_is_mentioned(str(task or "").lower(), name.lower())
    delta = abs(source_score - template_score)
    confidence = "high" if delta >= 5 else "medium" if delta >= 2 else "low"
    if source_score > 0 and template_score > 0 and delta <= 2:
        confidence = "medium"
    return {
        "documentId": str(getattr(document, "documentId", "") or ""),
        "name": name,
        "mentionedInTask": mentioned,
        "sourceScore": source_score,
        "templateScore": template_score,
        "confidence": confidence,
        "role": "unselected",
        "isSource": False,
        "isTemplate": False,
        "reasons": [*source_reasons[:4], *template_reasons[:4]],
    }


def _score_source_document(document: Any, task: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    name = str(getattr(document, "name", "") or "")
    lowered_name = name.lower()
    task_lower = str(task or "").lower()

    if _document_is_mentioned(task_lower, lowered_name):
        score += 2
        reasons.append("任务中提到了该 workbook。")
    for hint in SOURCE_DOCUMENT_HINTS:
        if hint in lowered_name:
            score += 3
            reasons.append(f"文件名包含源数据提示“{hint}”。")

    for sheet in getattr(document, "structuredData", {}).get("sheets", []) or []:
        if not isinstance(sheet, dict):
            continue
        title = str(sheet.get("title") or "")
        title_lower = title.lower()
        row_count = int(sheet.get("rowCount", 0) or 0)
        numeric_columns = [str(item) for item in sheet.get("numericColumns", []) or [] if str(item).strip()]
        sheet_role = str(sheet.get("sheetRole") or "")

        if sheet_role == "source_like":
            score += 4
            reasons.append(f"工作表“{title}”被解析为 source_like。")
        if row_count and numeric_columns:
            score += 5 if row_count >= 5 else 3
            reasons.append(f"工作表“{title}”有 {row_count} 行数据和 {len(numeric_columns)} 个数值列。")
        if any(hint in title_lower for hint in SOURCE_SHEET_HINTS):
            score += 2
            reasons.append(f"工作表名“{title}”像明细数据。")

    return score, _dedupe_reasons(reasons)


def _score_template_document(document: Any, task: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    name = str(getattr(document, "name", "") or "")
    lowered_name = name.lower()
    task_lower = str(task or "").lower()

    if _document_is_mentioned(task_lower, lowered_name):
        score += 2
        reasons.append("任务中提到了该 workbook。")
    for hint in TEMPLATE_DOCUMENT_HINTS:
        if hint in lowered_name:
            score += 3
            reasons.append(f"文件名包含模板提示“{hint}”。")

    for sheet in getattr(document, "structuredData", {}).get("sheets", []) or []:
        if not isinstance(sheet, dict):
            continue
        title = str(sheet.get("title") or "")
        title_lower = title.lower()
        headers = [str(item) for item in sheet.get("headers", []) or [] if str(item).strip()]
        row_count = int(sheet.get("rowCount", 0) or 0)
        label_anchor_count = len(sheet.get("labelAnchors", []) or [])
        empty_value_zone_count = len(sheet.get("emptyValueZones", []) or [])
        sheet_role = str(sheet.get("sheetRole") or "")

        if sheet_role == "template_like":
            score += 4
            reasons.append(f"工作表“{title}”被解析为 template_like。")
        if any(hint in title_lower for hint in TEMPLATE_SHEET_HINTS):
            score += 2
            reasons.append(f"工作表名“{title}”像模板或汇总页。")
        if _has_metric_result_headers(headers):
            score += 5
            reasons.append(f"工作表“{title}”有指标/结果类表头。")
        if label_anchor_count:
            score += min(label_anchor_count, 3) * 2
            reasons.append(f"工作表“{title}”检测到 {label_anchor_count} 个标签锚点。")
        if empty_value_zone_count:
            score += min(empty_value_zone_count, 3)
            reasons.append(f"工作表“{title}”检测到 {empty_value_zone_count} 个候选空白值位。")
        if row_count <= 3 and not sheet.get("numericColumns"):
            score += 1

    return score, _dedupe_reasons(reasons)


def _select_role_document_ids(role_items: list[dict[str, object]], *, role: str) -> list[str]:
    source_key = "sourceScore"
    template_key = "templateScore"
    if role == "source":
        mentioned_source_items = [
            item
            for item in role_items
            if bool(item.get("mentionedInTask")) and int(item[source_key]) >= 5
        ]
        if mentioned_source_items:
            return [str(item["documentId"]) for item in mentioned_source_items if str(item.get("documentId") or "").strip()]
        selected = [
            item
            for item in role_items
            if int(item[source_key]) > 0 and int(item[source_key]) >= int(item[template_key])
        ]
        if not selected:
            selected = [max(role_items, key=lambda item: int(item[source_key]))]
    else:
        mentioned_template_items = [
            item
            for item in role_items
            if bool(item.get("mentionedInTask")) and int(item[template_key]) >= 5
        ]
        if mentioned_template_items:
            return [str(item["documentId"]) for item in mentioned_template_items if str(item.get("documentId") or "").strip()]
        selected = [
            item
            for item in role_items
            if int(item[template_key]) > 0 and int(item[template_key]) >= int(item[source_key])
        ]
        if not selected:
            non_source = [
                item
                for item in role_items
                if int(item[source_key]) < max(int(candidate[source_key]) for candidate in role_items)
            ]
            selected = [max(non_source or role_items, key=lambda item: int(item[template_key]))]

    return [str(item["documentId"]) for item in selected if str(item.get("documentId") or "").strip()]


def _summarize_selected_documents(
    role_items: list[dict[str, object]],
    document_ids: list[str],
) -> list[dict[str, object]]:
    id_set = set(document_ids)
    return [
        {
            "documentId": item["documentId"],
            "name": item["name"],
            "sourceScore": item["sourceScore"],
            "templateScore": item["templateScore"],
            "confidence": item["confidence"],
        }
        for item in role_items
        if str(item["documentId"]) in id_set
    ]


def _build_role_warnings(
    role_items: list[dict[str, object]],
    source_documents: list[dict[str, object]],
    template_documents: list[dict[str, object]],
) -> list[str]:
    warnings: list[str] = []
    if not source_documents:
        warnings.append("未能稳定识别源数据 workbook。")
    if not template_documents:
        warnings.append("未能稳定识别待填模板 workbook。")
    if len(role_items) > 1 and set(item["documentId"] for item in source_documents) & set(item["documentId"] for item in template_documents):
        warnings.append("源数据和模板角色存在重叠，后续会继续按候选单元格审计。")
    if any(item.get("confidence") == "low" for item in role_items):
        warnings.append("部分 workbook 角色置信度较低。")
    return warnings


def _document_is_mentioned(task_lower: str, lowered_name: str) -> bool:
    if not lowered_name:
        return False
    stem = lowered_name.rsplit(".", 1)[0] if "." in lowered_name else lowered_name
    return lowered_name in task_lower or (stem and stem in task_lower)


def _has_metric_result_headers(headers: list[str]) -> bool:
    normalized = {str(header).strip().lower() for header in headers}
    metric_headers = {"指标", "metric", "metrics"}
    result_headers = {"结果", "result", "value", "数值"}
    return bool(normalized & metric_headers) and bool(normalized & result_headers)


def _dedupe_reasons(reasons: list[str]) -> list[str]:
    return list(dict.fromkeys(reason for reason in reasons if reason))
