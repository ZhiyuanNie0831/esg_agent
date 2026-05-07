"""结果行整理工具。

表格计算技能返回的是偏分析型的数据结构：
- 一条结果对应一份文档 / 工作表 / 数值列
- 指标以 key/value 的形式存在
- 某些场景还会带分组计算结果

这个模块把它改造成扁平的结果行结构，方便同时用于：
- Markdown 预览
- Excel 导出
- 最终 artifacts 展示
"""

from __future__ import annotations

# 结果表的标准列顺序。
# 某次任务不一定会用到全部列，因此下游会再过滤出真正有值的列。
RESULT_HEADERS = ("文档", "工作表", "分组字段", "分组值", "数值字段", "指标", "结果")


def build_result_rows(result_items: list[dict[str, object]]) -> list[dict[str, object]]:
    """把计算结果展开成统一的结果行列表。"""
    rows: list[dict[str, object]] = []

    for item in result_items:
        grouped_metrics = item.get("groupedMetrics", [])
        if grouped_metrics:
            # 分组计算会被展开成“每个分组 + 每个指标”一行。
            rows.extend(_build_grouped_rows(item, grouped_metrics))
            continue

        # 普通计算则是“每个指标”一行。
        rows.extend(_build_metric_rows(item))

    return rows


def resolve_present_headers(rows: list[dict[str, object]]) -> list[str]:
    """返回当前结果里真正有值的列。"""
    return [
        header
        for header in RESULT_HEADERS
        if any(row.get(header) not in (None, "") for row in rows)
    ]


def build_markdown_table(headers: list[str], rows: list[dict[str, object]]) -> str:
    """把结果行渲染成用于聊天区和最终输出的 Markdown 表格。"""
    if not headers or not rows:
        return "# 结果表\n\n暂无可填写内容。"

    markdown_rows = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        markdown_rows.append(
            "| " + " | ".join(str(row.get(header, "")) for header in headers) + " |"
        )

    return "\n".join(["# 结果表", "", *markdown_rows])


def _build_grouped_rows(
    item: dict[str, object],
    grouped_metrics: list[dict[str, object]],
) -> list[dict[str, object]]:
    """把分组计算结果展开成结果行。"""
    rows: list[dict[str, object]] = []

    for grouped in grouped_metrics:
        metrics = grouped.get("metrics", {})
        if not isinstance(metrics, dict):
            continue

        for metric_name, metric_value in metrics.items():
            rows.append(
                {
                    "文档": item.get("document"),
                    "工作表": item.get("sheet"),
                    "分组字段": item.get("groupBy"),
                    "分组值": grouped.get("group"),
                    "数值字段": item.get("column"),
                    "指标": metric_name,
                    "结果": metric_value,
                }
            )

    return rows


def _build_metric_rows(item: dict[str, object]) -> list[dict[str, object]]:
    """把非分组计算结果展开成结果行。"""
    metrics = item.get("metrics", {})
    if not isinstance(metrics, dict):
        return []

    rows: list[dict[str, object]] = []
    for metric_name, metric_value in metrics.items():
        rows.append(
            {
                "文档": item.get("document"),
                "工作表": item.get("sheet"),
                "数值字段": item.get("column"),
                "指标": metric_name,
                "结果": metric_value,
            }
        )

    return rows
