"""统一的标签文案映射。"""

INTENT_LABELS = {
    "review": "审核",
    "count": "统计",
    "summarize": "总结",
    "revise": "修订",
    "check_missing": "缺件检查",
    "general": "通用处理",
}

DOCUMENT_KIND_LABELS = {
    "invoice": "发票",
    "receipt": "收据",
    "contract": "合同",
    "statement": "对账单",
    "resume": "简历",
    "report": "报告",
    "general": "通用文档",
}

SKILL_LABELS = {
    "document_reader": "读取文档",
    "document_counter": "统计文档",
    "document_summarizer": "总结文档",
    "document_reviser": "修订草稿",
    "esg_material_checker": "检查 ESG 材料",
    "esg_standard_selector": "选择 ESG 标准",
    "esg_disclosure_mapper": "映射 ESG 披露主题",
    "esg_disclosure_matrix_builder": "构建 ESG 披露矩阵",
    "esg_kpi_extractor": "提取 ESG 指标",
    "esg_data_request_builder": "生成 ESG 补资料清单",
    "esg_evidence_linker": "链接 ESG 证据",
    "esg_report_outline_builder": "生成 ESG 报告大纲",
    "esg_report_writer": "生成 ESG 报告",
    "excel_role_classifier": "识别 Excel 角色",
    "calculation_planner": "规划表格计算",
    "spreadsheet_calculator": "表格计算",
    "table_mapping_preview": "预览填表映射",
    "table_filler": "按要求填表",
    "table_data_transfer": "源表写入目标表",
    "fill_validator": "校验填表结果",
}


def intent_label(intent_type: str) -> str:
    """把内部意图类型转换成中文标签。"""
    return INTENT_LABELS.get(intent_type, intent_type)


def join_intent_labels(intent_types: list[str]) -> str:
    """拼接多个意图标签。"""
    return "、".join(intent_label(intent_type) for intent_type in intent_types)


def document_kind_label(kind: str) -> str:
    """把内部文档类别转换成中文标签。"""
    return DOCUMENT_KIND_LABELS.get(kind, kind)


def join_document_kind_labels(kinds: list[str]) -> str:
    """拼接多个文档类别标签。"""
    return "、".join(document_kind_label(kind) for kind in kinds)


def skill_label(skill_name: str) -> str:
    """把技能名称转换成中文标签。"""
    return SKILL_LABELS.get(skill_name, skill_name)


def join_skill_labels(skill_names: list[str]) -> str:
    """拼接多个技能标签。"""
    return "、".join(skill_label(skill_name) for skill_name in skill_names)
