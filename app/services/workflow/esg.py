"""ESG 领域规则工具。

集中定义 ESG 任务识别、主题覆盖、指标提取和大纲生成所需的规则与辅助函数。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.schemas.workflow import DocumentSegment, PreparedDocument
from app.services.workflow.evidence import format_segment_location

ESG_TASK_KEYWORDS = (
    "esg",
    "可持续",
    "可持续发展",
    "双碳",
    "气候",
    "排放",
    "环境",
    "社会",
    "治理",
    "供应链",
    "人权",
    "反舞弊",
    "反腐败",
    "培训覆盖率",
    "董事会",
)
ESG_GAP_KEYWORDS = ("缺件", "缺失", "齐全", "完整", "覆盖", "缺口", "gap", "coverage")
ESG_KPI_KEYWORDS = (
    "指标",
    "kpi",
    "scope",
    "排放",
    "占比",
    "比例",
    "覆盖率",
    "次数",
    "数据",
    "台账",
    "统计",
    "metric",
)
ESG_OUTLINE_KEYWORDS = ("章节", "大纲", "outline", "结构", "框架", "披露结构", "目录")
ESG_REPORT_WRITING_KEYWORDS = (
    "生成",
    "撰写",
    "写一份",
    "写成",
    "输出",
    "形成",
    "起草",
    "草拟",
    "整理成",
    "编写",
    "write",
    "compose",
    "generate",
    "draft",
    "produce",
)
ESG_FULL_REPORT_HINTS = (
    "完整报告",
    "报告正文",
    "正式报告",
    "报告初稿",
    "报告草稿",
    "全文",
    "成稿",
    "一份 esg 报告",
    "一份esg报告",
    "esg report",
)
ESG_SECTION_ONLY_HINTS = ("章节", "这段", "段落", "小节", "section")
REPORT_WORD_COUNT_PATTERN = re.compile(
    r"(?P<value>\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<unit>万|千|k|K)?\s*(?P<label>字|词|words?|word)",
    re.IGNORECASE,
)
REPORT_WORD_COUNT_RANGE_PATTERN = re.compile(
    r"(?P<min>\d+(?:,\d{3})*)\s*(?:-|~|到|至)\s*(?P<max>\d+(?:,\d{3})*)\s*(?P<label>字|词|words?|word)",
    re.IGNORECASE,
)

PILLAR_LABELS = {
    "environment": "环境",
    "social": "社会",
    "governance": "治理",
}

PILLAR_KEYWORDS = {
    "environment": (
        "environment",
        "环境",
        "climate",
        "气候",
        "emission",
        "排放",
        "scope 1",
        "scope 2",
        "scope 3",
        "能耗",
        "energy",
        "renewable",
        "可再生",
        "waste",
        "废弃物",
        "water",
        "水耗",
    ),
    "social": (
        "social",
        "社会",
        "员工",
        "employee",
        "training",
        "培训",
        "safety",
        "安全",
        "diversity",
        "多元",
        "women",
        "女性",
        "supplier",
        "供应商",
        "human rights",
        "人权",
        "community",
        "社区",
    ),
    "governance": (
        "governance",
        "治理",
        "board",
        "董事会",
        "committee",
        "委员会",
        "anti-bribery",
        "反舞弊",
        "anti-corruption",
        "反腐败",
        "compliance",
        "合规",
        "audit",
        "审计",
        "risk",
        "风控",
        "举报",
        "grievance",
    ),
}

INDICATOR_RULES = (
    {"metric": "可再生电力占比", "pillar": "environment", "keywords": ("可再生电力", "renewable electricity", "renewable power"), "preferred_units": {"%"}},
    {"metric": "范围一排放", "pillar": "environment", "keywords": ("scope 1", "范围一"), "preferred_units": {"吨", "tco2e", "kg", "万吨"}},
    {"metric": "范围二排放", "pillar": "environment", "keywords": ("scope 2", "范围二"), "preferred_units": {"吨", "tco2e", "kg", "万吨", "%"}},
    {"metric": "范围三排放", "pillar": "environment", "keywords": ("scope 3", "范围三"), "preferred_units": {"吨", "tco2e", "kg", "万吨"}},
    {"metric": "培训覆盖率", "pillar": "social", "keywords": ("培训覆盖率", "training coverage", "培训覆盖"), "preferred_units": {"%"}},
    {"metric": "女性管理者占比", "pillar": "social", "keywords": ("女性管理者", "female manager", "women in management"), "preferred_units": {"%"}},
    {"metric": "员工流失率", "pillar": "social", "keywords": ("离职率", "turnover rate", "attrition"), "preferred_units": {"%"}},
    {"metric": "安全事故率", "pillar": "social", "keywords": ("安全事故", "injury rate", "ltifr"), "preferred_units": {"%", "次"}},
    {"metric": "ESG 委员会会议次数", "pillar": "governance", "keywords": ("committee met", "委员会召开", "委员会会议", "board esg committee"), "preferred_units": {"次"}},
    {"metric": "反舞弊培训覆盖率", "pillar": "governance", "keywords": ("anti-bribery training", "反舞弊培训", "anti-corruption training"), "preferred_units": {"%"}},
    {"metric": "供应商审核数量", "pillar": "social", "keywords": ("supplier audit", "供应商审核", "supplier review"), "preferred_units": {"家", "次", "个"}},
)

NUMBER_PATTERN = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|次|家|人|吨|tco2e|万吨|kg|小时|项|个|times?|meetings?)?",
    re.IGNORECASE,
)

GRI_TOPICS_PATH = Path(__file__).with_name("gri_topics.json")


def _load_gri_topics() -> list[dict[str, Any]]:
    try:
        payload = json.loads(GRI_TOPICS_PATH.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover - defensive default
        payload = []
    topics: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        topics.append(
            {
                "topic": str(item.get("topicId") or "").strip(),
                "label": str(item.get("label") or "").strip(),
                "pillar": str(item.get("pillar") or "environment").strip(),
                "keywords": tuple(str(alias).lower() for alias in item.get("aliases", []) if str(alias).strip()),
                "requiredDocumentKinds": [
                    str(kind).strip()
                    for kind in item.get("requiredDocumentKinds", [])
                    if str(kind).strip()
                ],
                "kpiPatterns": [
                    str(pattern).lower().strip()
                    for pattern in item.get("kpiPatterns", [])
                    if str(pattern).strip()
                ],
                "weakEvidenceThreshold": max(1, int(item.get("weakEvidenceThreshold", 2) or 2)),
            }
        )
    return topics


TOPIC_RULES = tuple(_load_gri_topics())


def is_esg_task(task: str) -> bool:
    """判断当前任务是否属于 ESG 场景。"""
    lowered = str(task or "").lower()
    return any(keyword in lowered for keyword in ESG_TASK_KEYWORDS)


def needs_esg_material_check(task: str, intent_types: list[str]) -> bool:
    """判断是否需要执行 ESG 材料完整性检查。"""
    lowered = str(task or "").lower()
    return "check_missing" in intent_types or any(keyword in lowered for keyword in ESG_GAP_KEYWORDS)


def needs_esg_kpi_extraction(task: str, intent_types: list[str]) -> bool:
    """判断是否需要抽取 ESG 指标。"""
    lowered = str(task or "").lower()
    return "count" in intent_types or any(keyword in lowered for keyword in ESG_KPI_KEYWORDS)


def needs_esg_outline(task: str, intent_types: list[str]) -> bool:
    """判断是否需要生成 ESG 大纲。"""
    lowered = str(task or "").lower()
    return "revise" in intent_types or any(keyword in lowered for keyword in ESG_OUTLINE_KEYWORDS)


def needs_esg_report_writing(task: str, intent_types: list[str]) -> bool:
    """判断是否需要从材料直接生成 ESG 报告正文。"""
    lowered = str(task or "").lower()
    if not is_esg_task(lowered):
        return False

    has_report_signal = "报告" in lowered or "report" in lowered
    if not has_report_signal:
        return False

    has_outline_signal = any(keyword in lowered for keyword in ESG_OUTLINE_KEYWORDS)
    has_section_only_signal = any(keyword in lowered for keyword in ESG_SECTION_ONLY_HINTS)
    has_full_report_hint = any(keyword in lowered for keyword in ESG_FULL_REPORT_HINTS)
    has_writing_action = any(keyword in lowered for keyword in ESG_REPORT_WRITING_KEYWORDS)
    has_word_count = resolve_esg_report_word_count(task)["explicit"]

    if has_outline_signal and not has_full_report_hint and not has_word_count:
        return False
    if has_section_only_signal and not has_full_report_hint and not has_word_count:
        return False
    return has_full_report_hint or has_word_count or (has_writing_action and has_report_signal)


def resolve_esg_report_word_count(task: str) -> dict[str, Any]:
    """从任务中提取客户指定的 ESG 报告字数。"""
    normalized_task = str(task or "")
    range_match = REPORT_WORD_COUNT_RANGE_PATTERN.search(normalized_task)
    if range_match:
        min_count = _parse_count_number(range_match.group("min"), "")
        max_count = _parse_count_number(range_match.group("max"), "")
        if min_count and max_count:
            lower = max(300, min(min_count, max_count))
            upper = min(20000, max(min_count, max_count))
            target = int(round((lower + upper) / 2))
            return {
                "explicit": True,
                "targetWordCount": target,
                "minWordCount": lower,
                "maxWordCount": upper,
                "label": range_match.group("label") or "字",
                "description": f"{lower}-{upper} 字",
            }

    match = REPORT_WORD_COUNT_PATTERN.search(normalized_task)
    if match:
        count = _parse_count_number(match.group("value"), match.group("unit") or "")
        if count:
            target = min(20000, max(300, count))
            tolerance = max(120, int(round(target * 0.1)))
            return {
                "explicit": True,
                "targetWordCount": target,
                "minWordCount": max(300, target - tolerance),
                "maxWordCount": min(20000, target + tolerance),
                "label": match.group("label") or "字",
                "description": f"约 {target} 字",
            }

    return {
        "explicit": False,
        "targetWordCount": 3000,
        "minWordCount": 2700,
        "maxWordCount": 3300,
        "label": "字",
        "description": "未识别客户指定字数，默认约 3000 字",
    }


def collect_esg_coverage(documents: list[PreparedDocument]) -> dict[str, Any]:
    """统计 ESG 支柱和主题覆盖情况。"""
    pillar_documents = {pillar: set() for pillar in PILLAR_LABELS}
    pillar_evidence_count = {pillar: 0 for pillar in PILLAR_LABELS}
    topic_coverage: dict[str, dict[str, Any]] = {}

    for document, segment in _iter_document_segments(documents):
        lowered = segment.text.lower()
        for pillar, keywords in PILLAR_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                pillar_documents[pillar].add(document.name)
                pillar_evidence_count[pillar] += 1

        for rule in TOPIC_RULES:
            if not any(keyword in lowered for keyword in rule["keywords"]):
                continue
            entry = topic_coverage.setdefault(
                rule["topic"],
                {
                    "topic": rule["topic"],
                    "label": rule["label"],
                    "pillar": rule["pillar"],
                    "requiredDocumentKinds": list(rule.get("requiredDocumentKinds", [])),
                    "weakEvidenceThreshold": int(rule.get("weakEvidenceThreshold", 2) or 2),
                    "documents": set(),
                    "evidenceCount": 0,
                    "sampleEvidence": segment.text[:180],
                    "sampleLocation": format_segment_location(segment),
                    "sampleDocumentId": document.documentId,
                    "sampleDocument": document.name,
                },
            )
            entry["documents"].add(document.name)
            entry["evidenceCount"] += 1

    pillar_coverage = {
        pillar: {
            "label": PILLAR_LABELS[pillar],
            "documentCount": len(pillar_documents[pillar]),
            "evidenceCount": pillar_evidence_count[pillar],
            "documents": sorted(pillar_documents[pillar]),
        }
        for pillar in PILLAR_LABELS
    }
    missing_pillars = [pillar for pillar, details in pillar_coverage.items() if details["documentCount"] == 0]
    normalized_topics = [
        {
            **entry,
            "documents": sorted(entry["documents"]),
        }
        for entry in topic_coverage.values()
    ]
    normalized_topics.sort(key=lambda item: (item["pillar"], -int(item["evidenceCount"]), item["label"]))
    topic_matrix = []
    missing_required_kinds: set[str] = set()
    for rule in TOPIC_RULES:
        matched = next((item for item in normalized_topics if item["topic"] == rule["topic"]), None)
        evidence_count = int(matched["evidenceCount"]) if matched else 0
        if matched is None:
            status = "missing"
        elif evidence_count < int(rule.get("weakEvidenceThreshold", 2) or 2):
            status = "weak"
        else:
            status = "covered"
        if status in {"missing", "weak"}:
            missing_required_kinds.update(rule.get("requiredDocumentKinds", []))
        topic_matrix.append(
            {
                "topic": rule["topic"],
                "label": rule["label"],
                "pillar": rule["pillar"],
                "status": status,
                "requiredDocumentKinds": list(rule.get("requiredDocumentKinds", [])),
                "documents": matched["documents"] if matched else [],
                "evidenceCount": evidence_count,
                "sampleEvidence": matched.get("sampleEvidence") if matched else "",
                "sampleLocation": matched.get("sampleLocation") if matched else "",
                "sampleDocument": matched.get("sampleDocument") if matched else "",
                "sampleDocumentId": matched.get("sampleDocumentId") if matched else None,
            }
        )
    return {
        "pillarCoverage": pillar_coverage,
        "missingPillars": missing_pillars,
        "topicCoverage": normalized_topics,
        "topicMatrix": topic_matrix,
        "recommendedDocumentKinds": sorted(missing_required_kinds),
    }


def extract_esg_indicators(documents: list[PreparedDocument]) -> list[dict[str, Any]]:
    """从文档片段中抽取 ESG 指标和值。"""
    indicators: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for document, segment in _iter_document_segments(documents):
        lowered = segment.text.lower()
        for rule in INDICATOR_RULES:
            if not any(keyword in lowered for keyword in rule["keywords"]):
                continue
            value, unit = _select_indicator_value(segment.text, preferred_units=rule["preferred_units"])
            if value is None:
                continue
            item = {
                "metric": rule["metric"],
                "pillar": rule["pillar"],
                "value": value,
                "unit": unit,
                "sourceDocument": document.name,
                "sourceDocumentId": document.documentId,
                "sourceSegmentId": segment.segmentId,
                "sourceLocation": format_segment_location(segment),
                "evidence": segment.text[:220],
                "topicId": _match_gri_topic_for_indicator(rule["keywords"], segment.text),
            }
            key = (item["metric"], item["sourceDocument"], item["sourceSegmentId"])
            if key in seen_keys:
                continue
            indicators.append(item)
            seen_keys.add(key)

    indicators.sort(key=lambda item: (item["pillar"], item["metric"], item["sourceDocument"]))
    return indicators


def build_esg_outline(documents: list[PreparedDocument]) -> dict[str, Any]:
    coverage = collect_esg_coverage(documents)
    indicators = extract_esg_indicators(documents)
    sections = [
        "# ESG 报告建议大纲",
        "## 1. 报告说明",
        "- 披露范围、边界、统计口径与时间区间",
        "- 关键假设、数据来源与第三方鉴证情况",
    ]

    for pillar in ("environment", "social", "governance"):
        sections.append(f"## {PILLAR_LABELS[pillar]}")
        topic_lines = [
            f"- {topic['label']}（{_topic_status_label(topic.get('status', 'covered'))}）"
            for topic in coverage["topicMatrix"]
            if topic["pillar"] == pillar
        ]
        if topic_lines:
            sections.extend(topic_lines)
        else:
            sections.append(f"- 建议补充 {PILLAR_LABELS[pillar]} 相关披露主题与证明材料")

    if indicators:
        sections.append("## 关键指标附表")
        for indicator in indicators[:8]:
            sections.append(
                f"- {indicator['metric']}：{indicator['value']}{indicator['unit']} "
                f"({indicator['sourceDocument']})"
            )

    recommendations: list[str] = []
    if coverage["missingPillars"]:
        recommendations.append(
            "补充这些 ESG 支柱的材料："
            + "、".join(PILLAR_LABELS[pillar] for pillar in coverage["missingPillars"])
        )
    if coverage["recommendedDocumentKinds"]:
        recommendations.append("建议优先补充这些文档类型：" + "、".join(coverage["recommendedDocumentKinds"]))
    if not indicators:
        recommendations.append("当前材料中缺少清晰可提取的 ESG 指标，建议补充 KPI 表或量化段落。")

    return {
        "outlineMarkdown": "\n".join(sections),
        "recommendations": recommendations,
        "missingPillars": coverage["missingPillars"],
        "coveredTopics": [topic["label"] for topic in coverage["topicMatrix"] if topic["status"] == "covered"],
        "topicMatrix": coverage["topicMatrix"],
    }


def estimate_report_word_count(markdown: str) -> int:
    """估算中英文混合报告的字数/词数。"""
    text = re.sub(r"[#*_>`\-\|\[\]\(\)]", " ", str(markdown or ""))
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    latin_words = re.findall(r"[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*", text)
    return len(chinese_chars) + len(latin_words)


def _parse_count_number(value: str, unit: str) -> int:
    try:
        number = float(str(value or "").replace(",", ""))
    except ValueError:
        return 0
    normalized_unit = str(unit or "").strip().lower()
    if normalized_unit == "万":
        number *= 10000
    elif normalized_unit in {"千", "k"}:
        number *= 1000
    return int(round(number))


def select_esg_standards(task: str, documents: list[PreparedDocument]) -> dict[str, Any]:
    """根据任务和材料选择 ESG 报告应优先对齐的标准体系。"""
    haystack = " ".join([str(task or ""), *(document.textPreview or document.text for document in documents)]).lower()
    selected: list[dict[str, Any]] = []

    def add_standard(code: str, name: str, reason: str, priority: int) -> None:
        if any(item["code"] == code for item in selected):
            return
        selected.append({"code": code, "name": name, "reason": reason, "priority": priority})

    add_standard("GRI", "GRI Standards", "ESG 报告通用披露默认对齐 GRI 主题体系。", 1)
    if any(keyword in haystack for keyword in ("ifrs", "issb", "s1", "s2", "气候", "climate", "scope", "排放", "财务影响", "风险")):
        add_standard("ISSB", "IFRS S1 / IFRS S2", "任务或材料包含气候、排放、风险或可持续财务披露信号。", 2)
    if any(keyword in haystack for keyword in ("esrs", "csrd", "欧盟", "欧洲", "double materiality", "双重重要性")):
        add_standard("ESRS", "European Sustainability Reporting Standards", "任务或材料包含欧盟/ESRS/双重重要性信号。", 3)
    if any(keyword in haystack for keyword in ("港交所", "hkex", "联交所")):
        add_standard("HKEX", "HKEX ESG Reporting Guide", "任务或材料包含港交所披露信号。", 4)
    if any(keyword in haystack for keyword in ("上交所", "深交所", "北交所", "可持续发展报告指引")):
        add_standard("CN_EXCHANGE", "中国交易所可持续发展报告指引", "任务或材料包含中国交易所披露信号。", 5)

    selected.sort(key=lambda item: int(item["priority"]))
    return {
        "standards": selected,
        "primaryStandard": selected[0]["code"] if selected else None,
        "reportingBasis": [item["code"] for item in selected],
    }


def build_esg_disclosure_matrix(
    documents: list[PreparedDocument],
    *,
    standards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构建 ESG 披露矩阵，把标准主题、覆盖状态和缺口放到一张表里。"""
    coverage = collect_esg_coverage(documents)
    indicators = extract_esg_indicators(documents)
    standard_codes = [str(item.get("code") or "") for item in standards or [] if str(item.get("code") or "")]
    if not standard_codes:
        standard_codes = ["GRI"]

    indicator_topics = {
        str(indicator.get("topicId") or "")
        for indicator in indicators
        if str(indicator.get("topicId") or "")
    }
    matrix_items = []
    for topic in coverage["topicMatrix"]:
        topic_id = str(topic.get("topic") or "")
        kpi_status = "available" if topic_id in indicator_topics else "missing"
        required_data = _build_required_data_for_topic(topic, kpi_status=kpi_status)
        matrix_items.append(
            {
                "disclosureId": topic_id,
                "standard": "GRI",
                "alsoRelevantTo": _related_standards_for_topic(topic, standard_codes),
                "pillar": topic.get("pillar"),
                "topic": topic.get("label"),
                "status": topic.get("status"),
                "kpiStatus": kpi_status,
                "requiredData": required_data,
                "requiredDocumentKinds": topic.get("requiredDocumentKinds", []),
                "evidenceCount": topic.get("evidenceCount", 0),
                "sampleDocument": topic.get("sampleDocument", ""),
                "sampleLocation": topic.get("sampleLocation", ""),
                "nextAction": _build_disclosure_next_action(topic, required_data),
            }
        )

    stats = {
        "covered": len([item for item in matrix_items if item["status"] == "covered"]),
        "weak": len([item for item in matrix_items if item["status"] == "weak"]),
        "missing": len([item for item in matrix_items if item["status"] == "missing"]),
        "total": len(matrix_items),
    }
    return {
        "matrix": matrix_items,
        "stats": stats,
        "standards": standard_codes,
        "coverage": coverage,
    }


def build_esg_data_requests(
    matrix_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """根据披露矩阵生成补资料/追数清单。"""
    requests: list[dict[str, Any]] = []
    for item in matrix_items:
        status = str(item.get("status") or "")
        kpi_status = str(item.get("kpiStatus") or "")
        if status == "covered" and kpi_status == "available":
            continue
        pillar = str(item.get("pillar") or "")
        requests.append(
            {
                "requestId": f"req_{len(requests) + 1}",
                "topic": item.get("topic"),
                "disclosureId": item.get("disclosureId"),
                "owner": _default_owner_for_pillar(pillar),
                "priority": "high" if status == "missing" else "medium",
                "requiredData": item.get("requiredData", []),
                "requiredDocumentKinds": item.get("requiredDocumentKinds", []),
                "reason": item.get("nextAction"),
                "status": "open",
            }
        )
    return requests


def build_esg_evidence_links(documents: list[PreparedDocument]) -> list[dict[str, Any]]:
    """把披露主题和 KPI 与原始证据连接起来，形成审计索引。"""
    coverage = collect_esg_coverage(documents)
    indicators = extract_esg_indicators(documents)
    links: list[dict[str, Any]] = []

    for topic in coverage["topicMatrix"]:
        if not topic.get("sampleDocument"):
            continue
        links.append(
            {
                "linkId": f"link_{len(links) + 1}",
                "type": "topic",
                "claim": f"{topic.get('label')}：{_topic_status_label(str(topic.get('status') or 'missing'))}",
                "disclosureId": topic.get("topic"),
                "document": topic.get("sampleDocument"),
                "documentId": topic.get("sampleDocumentId"),
                "location": topic.get("sampleLocation"),
                "excerpt": topic.get("sampleEvidence"),
                "supportLevel": "supported" if topic.get("status") == "covered" else "weak",
            }
        )

    for indicator in indicators:
        links.append(
            {
                "linkId": f"link_{len(links) + 1}",
                "type": "kpi",
                "claim": f"{indicator.get('metric')}={indicator.get('value')}{indicator.get('unit')}",
                "disclosureId": indicator.get("topicId"),
                "document": indicator.get("sourceDocument"),
                "documentId": indicator.get("sourceDocumentId"),
                "location": indicator.get("sourceLocation"),
                "excerpt": indicator.get("evidence"),
                "supportLevel": "supported",
            }
        )

    return links


def build_esg_material_summary(coverage: dict[str, Any]) -> str:
    parts = [
        f"{details['label']} {details['documentCount']} 份"
        for details in coverage["pillarCoverage"].values()
    ]
    missing = coverage["missingPillars"]
    topic_matrix = coverage.get("topicMatrix", [])
    covered_count = len([item for item in topic_matrix if item.get("status") == "covered"])
    weak_count = len([item for item in topic_matrix if item.get("status") == "weak"])
    missing_topic_count = len([item for item in topic_matrix if item.get("status") == "missing"])
    if missing:
        return (
            "ESG 材料覆盖："
            + "；".join(parts)
            + f"。GRI 主题矩阵：covered {covered_count} / weak {weak_count} / missing {missing_topic_count}。"
            + "待补齐："
            + "、".join(PILLAR_LABELS[pillar] for pillar in missing)
            + "。"
        )
    return (
        "ESG 材料覆盖："
        + "；".join(parts)
        + f"。GRI 主题矩阵：covered {covered_count} / weak {weak_count} / missing {missing_topic_count}。"
    )


def build_esg_indicator_summary(indicators: list[dict[str, Any]]) -> str:
    if not indicators:
        return "当前材料中尚未识别到可直接抽取的 ESG 指标。"

    snippets = [
        f"{indicator['metric']}={indicator['value']}{indicator['unit']}"
        for indicator in indicators[:5]
    ]
    return f"共识别 {len(indicators)} 个 ESG 指标：" + "；".join(snippets) + "。"


def build_esg_topic_evidence(
    topic_coverage: list[dict[str, Any]],
    *,
    source_step: str | None = None,
    limit: int = 5,
) -> list[dict[str, str]]:
    evidence_items: list[dict[str, str]] = []
    for topic in topic_coverage[:limit]:
        document_name = str(topic.get("sampleDocument") or "")
        excerpt = str(topic.get("sampleEvidence") or "").strip()
        location = str(topic.get("sampleLocation") or "正文定位未标注").strip()
        if not document_name or not excerpt:
            continue
        evidence_items.append(
            {
                "title": str(topic.get("label") or "ESG 主题"),
                "documentId": topic.get("sampleDocumentId"),
                "document": document_name,
                "location": location,
                "excerpt": excerpt,
                "sourceStep": source_step,
            }
        )
    return evidence_items


def build_esg_indicator_evidence(
    indicators: list[dict[str, Any]],
    *,
    source_step: str | None = None,
    limit: int = 5,
) -> list[dict[str, str]]:
    evidence_items: list[dict[str, str]] = []
    for indicator in indicators[:limit]:
        evidence_items.append(
            {
                "title": f"{indicator['metric']}：{indicator['value']}{indicator['unit']}",
                "documentId": indicator.get("sourceDocumentId"),
                "document": str(indicator.get("sourceDocument") or "未命名文档"),
                "location": str(indicator.get("sourceLocation") or "正文定位未标注"),
                "excerpt": str(indicator.get("evidence") or ""),
                "sourceStep": source_step,
                "segmentId": indicator.get("sourceSegmentId"),
            }
        )
    return evidence_items


def _iter_document_segments(documents: list[PreparedDocument]) -> list[tuple[PreparedDocument, DocumentSegment]]:
    items: list[tuple[PreparedDocument, DocumentSegment]] = []
    for document in documents:
        if document.segments:
            items.extend((document, segment) for segment in document.segments if segment.text.strip())
            continue
        items.append(
            (
                document,
                DocumentSegment(
                    segmentId=f"{document.name}_fallback",
                    kind="document",
                    label=document.name,
                    text=document.text,
                ),
            )
        )
    return items


def _select_indicator_value(text: str, *, preferred_units: set[str]) -> tuple[float | None, str]:
    matches = list(NUMBER_PATTERN.finditer(text))
    if not matches:
        return None, ""

    candidates = []
    for match in matches:
        value_text = match.group("value") or ""
        unit_text = _normalize_unit(match.group("unit") or "")
        try:
            value = float(value_text)
        except ValueError:
            continue
        if 1900 <= value <= 2100:
            continue
        score = 1.0
        if preferred_units and unit_text in preferred_units:
            score += 4.0
        elif preferred_units and "%" in preferred_units and unit_text == "%":
            score += 4.0
        if unit_text:
            score += 1.0
        candidates.append((score, value, unit_text))

    if not candidates:
        return None, ""

    candidates.sort(key=lambda item: (-item[0], item[1]))
    _, value, unit = candidates[0]
    return value, unit


def _normalize_unit(unit: str) -> str:
    lowered = str(unit or "").strip().lower()
    if lowered in {"times", "time", "meeting", "meetings"}:
        return "次"
    return lowered


def _build_required_data_for_topic(topic: dict[str, Any], *, kpi_status: str) -> list[str]:
    required = list(topic.get("requiredDocumentKinds", []) or [])
    label = str(topic.get("label") or "ESG 主题")
    if str(topic.get("status") or "") == "missing":
        required.append(f"{label}的政策、管理措施或年度进展")
    if kpi_status == "missing":
        required.append(f"{label}相关 KPI、单位、期间和统计边界")
    return list(dict.fromkeys(str(item) for item in required if str(item).strip()))


def _related_standards_for_topic(topic: dict[str, Any], standard_codes: list[str]) -> list[str]:
    pillar = str(topic.get("pillar") or "")
    related: list[str] = []
    if "ISSB" in standard_codes and pillar == "environment":
        related.append("ISSB")
    if "ESRS" in standard_codes:
        related.append("ESRS")
    if "HKEX" in standard_codes:
        related.append("HKEX")
    if "CN_EXCHANGE" in standard_codes:
        related.append("CN_EXCHANGE")
    return related


def _build_disclosure_next_action(topic: dict[str, Any], required_data: list[str]) -> str:
    status = str(topic.get("status") or "")
    label = str(topic.get("label") or "该主题")
    if status == "missing":
        return f"补充{label}的披露材料和量化数据。"
    if status == "weak":
        return f"增强{label}的证据数量、数据口径和管理措施说明。"
    if required_data:
        return f"补齐{label}的 KPI 口径或数据来源。"
    return "当前披露证据较完整，可进入正文撰写和一致性检查。"


def _default_owner_for_pillar(pillar: str) -> str:
    return {
        "environment": "EHS / 环境管理",
        "social": "HR / 供应链 / 安全管理",
        "governance": "董事会办公室 / 合规",
    }.get(pillar, "ESG 工作组")


def _match_gri_topic_for_indicator(keywords: tuple[str, ...], text: str) -> str | None:
    lowered = text.lower()
    for topic in TOPIC_RULES:
        topic_keywords = tuple(topic.get("keywords", ())) + tuple(topic.get("kpiPatterns", ()))
        if any(keyword in lowered for keyword in topic_keywords) or any(keyword in lowered for keyword in keywords):
            return str(topic.get("topic") or "") or None
    return None


def _topic_status_label(status: str) -> str:
    return {
        "covered": "已覆盖",
        "weak": "证据偏弱",
        "missing": "缺失",
    }.get(status, status)
