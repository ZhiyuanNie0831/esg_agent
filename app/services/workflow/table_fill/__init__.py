"""表格填表功能包。

这里把填表功能拆成两个部分：

1. `result_rows`
   把计算结果整理成稳定的行结构，供前端预览、Markdown 和 Excel 导出复用。
2. `workbook_export`
   把整理后的行写回 Excel 工作簿，尽量保留原始模板结构。
3. `fill_report`
   把写入审计整理成可下载的 Markdown 填写报告。

`TableFillerSkill` 只从这里取能力，因此技能层本身可以保持轻量，主要负责串联步骤。
"""

from app.services.workflow.table_fill.result_rows import (
    RESULT_HEADERS,
    build_markdown_table,
    build_result_rows,
    resolve_present_headers,
)
from app.services.workflow.table_fill.data_transfer import TableDataTransferExporter
from app.services.workflow.table_fill.fill_report import TableFillReportBuilder
from app.services.workflow.table_fill.workbook_export import TableFillWorkbookExporter

# 统一对外导出常用工具，调用方只需要引用这个包路径。
__all__ = [
    "RESULT_HEADERS",
    "TableDataTransferExporter",
    "TableFillWorkbookExporter",
    "TableFillReportBuilder",
    "build_markdown_table",
    "build_result_rows",
    "resolve_present_headers",
]
