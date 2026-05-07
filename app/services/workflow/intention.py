"""意图分析服务。

基于规则和可选 agent 共同判断用户任务类型、所需材料和推荐技能。
"""

from collections.abc import Iterable
from typing import Any

from app.schemas.workflow import IntentionAnalysis, PreparedDocument
from app.services.workflow.errors import require_local_fallback
from app.services.workflow.esg import (
    is_esg_task,
    needs_esg_kpi_extraction,
    needs_esg_material_check,
    needs_esg_outline,
    needs_esg_report_writing,
)
from app.services.workflow.text import join_document_kind_labels, join_intent_labels

INTENT_KEYWORDS = (
    (
        "check_missing",
        (
            "missing",
            "缺失",
            "缺件",
            "补齐",
            "核对材料",
            "缺什么",
            "少什么",
            "缺哪些",
            "缺哪",
            "是否齐全",
            "齐全",
            "完整吗",
            "完整性",
            "gap",
        ),
    ),
    (
        "revise",
        (
            "revise",
            "rewrite",
            "modify",
            "修改",
            "润色",
            "修订",
            "改写",
            "重写",
            "优化措辞",
            "更正式",
            "正式一点",
            "更清晰",
            "整理成稿",
            "改得",
        ),
    ),
    (
        "count",
        (
            "count",
            "数量",
            "统计",
            "多少",
            "几份",
            "算一下",
            "测算",
            "核算",
            "计算",
            "求和",
            "合计",
            "汇总",
            "平均",
            "平均值",
            "最大",
            "最小",
            "kpi",
        ),
    ),
    (
        "summarize",
        (
            "summary",
            "summarize",
            "总结",
            "概括",
            "摘要",
            "整理",
            "重点",
            "要点",
            "提炼",
            "提要",
            "概述",
            "结论",
            "管理层摘要",
            "一句话总结",
            "大纲",
            "提纲",
            "框架",
            "outline",
        ),
    ),
    (
        "review",
        (
            "review",
            "审核",
            "检查",
            "校验",
            "分析",
            "看一下",
            "看下",
            "看看",
            "帮我看",
            "阅读",
            "读一下",
            "读完",
            "看完",
            "审阅",
            "研读",
            "评估",
            "有什么问题",
            "哪里有问题",
        ),
    ),
)

SPREADSHEET_HINTS = (
    "excel",
    "spreadsheet",
    "xlsx",
    "xls",
    "表格",
    "工作表",
    "sheet",
    "台账",
    "明细",
    "数据表",
    "scope",
    "指标",
    "kpi",
)
CALCULATION_KEYWORDS = ("calculate", "calc", "sum", "total", "avg", "average", "计算", "求和", "合计", "汇总", "平均", "最大", "最小", "数值", "金额")
TABLE_FILL_KEYWORDS = (
    "fill the",
    "fill template",
    "fill form",
    "fill in",
    "fill out",
    "populate",
    "complete the template",
    "write into",
    "write to",
    "填表",
    "回填",
    "回填到",
    "填写",
    "填入",
    "填到",
    "写入",
    "写到",
    "填报",
)
TABLE_TARGET_HINTS = (
    "template",
    "form",
    "blank",
    "target workbook",
    "模板",
    "空白表",
    "空表",
    "目标表",
    "汇总表",
    "填报表",
    "待填",
)
DOCUMENT_REFERENCE_KEYWORDS = (
    "文档",
    "文件",
    "材料",
    "附件",
    "这份",
    "这些",
    "报销",
    "合同",
    "表格",
    "excel",
    "sheet",
)

DOCUMENT_RULES = {
    "报销": ["invoice", "receipt"],
    "reimbursement": ["invoice", "receipt"],
    "合同": ["contract"],
    "contract": ["contract"],
    "简历": ["resume"],
    "resume": ["resume"],
    "对账": ["statement", "invoice"],
    "reconcile": ["statement", "invoice"],
    "报告": ["report"],
    "report": ["report"],
}

DEFAULT_SKILLS_BY_INTENT = {
    "count": ["document_reader", "document_counter"],
    "summarize": ["document_reader", "document_summarizer"],
    "revise": ["document_reader", "document_summarizer", "document_reviser"],
    "check_missing": ["document_reader", "document_counter"],
    "review": ["document_reader", "document_summarizer"],
    "general": ["document_reader", "document_summarizer"],
}


class WorkflowIntentionService:
    """识别任务意图，并推断所需材料与技能。"""

    def __init__(self, agent_runtime: Any | None = None, *, local_fallback_enabled: bool = True) -> None:
        self._agent_runtime = agent_runtime
        self._local_fallback_enabled = local_fallback_enabled

    def analyze(
        self,
        task: str,
        documents: list[PreparedDocument],
        preferred_skills: list[str],
        available_skills: Iterable[Any] = (),
        agent_mode: str = "auto",
    ) -> IntentionAnalysis:
        """综合规则和 agent 结果，输出结构化意图分析。"""
        lowered = task.lower()
        available_skills = self._normalize_available_skills(available_skills)
        available_skill_name_set = {skill.name for skill in available_skills}
        detected_intent_types = self._detect_intent_types(lowered)
        intent_type = detected_intent_types[0]
        required_document_kinds = self._detect_required_document_kinds(lowered)
        unsupported_preferred_skills = [
            skill_name
            for skill_name in self._normalize_skill_names(preferred_skills)
            if available_skill_name_set and skill_name not in available_skill_name_set
        ]
        recommended_skills = self._build_recommended_skills(
            lowered,
            detected_intent_types,
            documents,
            preferred_skills,
            unsupported_preferred_skills,
        )
        document_required = self._detect_document_required(lowered, documents)
        confidence = self._build_confidence(detected_intent_types, documents)
        notes = ["当前意图分析使用确定性规则，方便你后续扩展而不用改执行器。"]

        agent_result = self._analyze_with_agent(
            task=task,
            documents=documents,
            preferred_skills=preferred_skills,
            available_skills=available_skills,
        )
        if agent_mode != "off" and agent_result is None:
            require_local_fallback(
                local_fallback_enabled=self._local_fallback_enabled,
                agent_active=self._agent_runtime is not None,
                capability="任务分析",
            )
        if agent_result is not None:
            detected_intent_types = self._normalize_intent_types(
                agent_result.get("detectedIntentTypes"),
                fallback=detected_intent_types,
            )
            intent_type = self._normalize_primary_intent(
                agent_result.get("intentType"),
                detected_intent_types=detected_intent_types,
                fallback=intent_type,
            )
            required_document_kinds = self._normalize_document_kinds(
                agent_result.get("requiredDocumentKinds"),
                fallback=required_document_kinds,
            )
            recommended_skills = self._normalize_skill_selection(
                agent_result.get("recommendedSkills"),
                available_skill_names=available_skill_name_set,
                fallback=recommended_skills,
                preferred_skills=preferred_skills,
                unsupported_preferred_skills=unsupported_preferred_skills,
            )
            document_required = self._normalize_bool(
                agent_result.get("documentRequired"),
                fallback=document_required,
            )
            confidence = self._normalize_confidence(
                agent_result.get("confidence"),
                fallback=confidence,
            )
            notes = ["当前意图分析由 agent 生成，规则引擎作为回退。"]
            notes.extend(self._normalize_notes(agent_result.get("notes")))

        notes = self._prepend_agent_mode_note(
            notes,
            agent_mode=agent_mode,
            agent_active=self._agent_runtime is not None,
            agent_used=agent_result is not None,
            local_fallback_enabled=self._local_fallback_enabled,
        )

        if len(detected_intent_types) > 1:
            notes.append(f"检测到复合型任务，当前会按“{join_intent_labels(detected_intent_types)}”串联规划。")
        if documents:
            notes.append(f"已收到 {len(documents)} 份标准化文档，可继续用于后续规划。")
        spreadsheet_count = sum(1 for document in documents if document.type == "excel")
        if spreadsheet_count:
            notes.append(f"检测到 {spreadsheet_count} 份表格文档，可执行读取、计算和填表类 skill。")
        if document_required and not documents:
            notes.append("当前任务明显依赖原始材料，但还没有上传文档，建议先补充文件再执行。")
        if required_document_kinds:
            notes.append(f"识别到需要这些文档类型：{join_document_kind_labels(required_document_kinds)}。")
        if unsupported_preferred_skills:
            notes.append(
                "这些手动指定的 skill 尚未注册，已自动忽略："
                f"{'、'.join(unsupported_preferred_skills)}。"
            )
        if recommended_skills:
            notes.append(
                f"当前规划会优先串联这些技能："
                f"{'、'.join(recommended_skills)}。"
            )

        return IntentionAnalysis(
            primaryGoal=task.strip(),
            intentType=intent_type,
            detectedIntentTypes=detected_intent_types,
            confidence=confidence,
            documentRequired=document_required,
            requiredDocumentKinds=required_document_kinds,
            recommendedSkills=recommended_skills,
            unsupportedPreferredSkills=unsupported_preferred_skills,
            notes=notes,
        )

    def _detect_intent_types(self, lowered_task: str) -> list[str]:
        detected = [
            intent_type
            for intent_type, keywords in INTENT_KEYWORDS
            if any(keyword in lowered_task for keyword in keywords)
        ]
        if "count" not in detected and any(keyword in lowered_task for keyword in CALCULATION_KEYWORDS):
            detected.append("count")
        if "summarize" not in detected and any(keyword in lowered_task for keyword in ("重点", "要点", "提炼", "概述")):
            detected.append("summarize")
        if "review" not in detected and any(keyword in lowered_task for keyword in ("看一下", "阅读", "审阅", "研读")):
            detected.append("review")
        return detected or ["general"]

    def _detect_required_document_kinds(self, lowered_task: str) -> list[str]:
        detected: list[str] = []

        for keyword, kinds in DOCUMENT_RULES.items():
            if keyword in lowered_task:
                if keyword in {"报告", "report"} and needs_esg_report_writing(lowered_task, []):
                    continue
                for kind in kinds:
                    if kind not in detected:
                        detected.append(kind)

        return detected

    def _build_recommended_skills(
        self,
        lowered_task: str,
        intent_types: list[str],
        documents: list[PreparedDocument],
        preferred_skills: list[str],
        unsupported_preferred_skills: list[str],
    ) -> list[str]:
        ordered_skills: list[str] = []

        for skill_name in self._normalize_skill_names(preferred_skills):
            if skill_name in unsupported_preferred_skills:
                continue
            if skill_name not in ordered_skills:
                ordered_skills.append(skill_name)

        for intent_type in intent_types:
            for skill_name in DEFAULT_SKILLS_BY_INTENT[intent_type]:
                self._append_unique_skill(ordered_skills, skill_name)

        if is_esg_task(lowered_task):
            esg_report_requested = needs_esg_report_writing(lowered_task, intent_types)
            self._append_unique_skill(ordered_skills, "esg_standard_selector", after_skill="document_reader")
            self._append_unique_skill(ordered_skills, "esg_disclosure_mapper", after_skill="esg_standard_selector")
            self._append_unique_skill(ordered_skills, "esg_disclosure_matrix_builder", after_skill="esg_disclosure_mapper")

            if needs_esg_material_check(lowered_task, intent_types):
                self._append_unique_skill(ordered_skills, "esg_material_checker", after_skill="esg_disclosure_matrix_builder")
                self._append_unique_skill(ordered_skills, "esg_data_request_builder", after_skill="esg_material_checker")

            if needs_esg_kpi_extraction(lowered_task, intent_types) or esg_report_requested:
                self._append_unique_skill(ordered_skills, "esg_kpi_extractor", after_skill="esg_disclosure_matrix_builder")
                self._append_unique_skill(ordered_skills, "esg_evidence_linker", after_skill="esg_kpi_extractor")
            elif needs_esg_outline(lowered_task, intent_types):
                self._append_unique_skill(ordered_skills, "esg_evidence_linker", after_skill="esg_disclosure_matrix_builder")

            if needs_esg_outline(lowered_task, intent_types) or esg_report_requested:
                self._append_unique_skill(ordered_skills, "esg_report_outline_builder", before_skill="document_reviser")

            if esg_report_requested:
                self._append_unique_skill(ordered_skills, "esg_report_writer", after_skill="esg_report_outline_builder")

        has_spreadsheet = any(document.type == "excel" for document in documents)
        spreadsheet_requested = has_spreadsheet or any(keyword in lowered_task for keyword in SPREADSHEET_HINTS)
        calculation_requested = any(keyword in lowered_task for keyword in CALCULATION_KEYWORDS)
        table_fill_requested = self._is_table_fill_request(lowered_task)

        if spreadsheet_requested:
            direct_transfer_requested = table_fill_requested and not calculation_requested
            if direct_transfer_requested:
                self._append_unique_skill(ordered_skills, "table_data_transfer")
            elif calculation_requested or table_fill_requested:
                self._append_unique_skill(ordered_skills, "spreadsheet_calculator")
            if table_fill_requested and not direct_transfer_requested:
                self._append_unique_skill(ordered_skills, "spreadsheet_calculator")
                self._append_unique_skill(ordered_skills, "table_filler")
        elif calculation_requested:
            self._append_unique_skill(ordered_skills, "spreadsheet_calculator")

        if len(documents) > 1 and "document_counter" not in ordered_skills:
            self._append_unique_skill(ordered_skills, "document_counter")

        return ordered_skills

    def _is_table_fill_request(self, lowered_task: str) -> bool:
        if any(keyword in lowered_task for keyword in TABLE_FILL_KEYWORDS):
            return True

        has_target_hint = any(keyword in lowered_task for keyword in TABLE_TARGET_HINTS)
        has_write_action = any(keyword in lowered_task for keyword in ("填", "写", "回填", "填写", "填入", "填到", "写入"))
        return has_target_hint and has_write_action

    def _detect_document_required(self, lowered_task: str, documents: list[PreparedDocument]) -> bool:
        if documents:
            return True
        if needs_esg_report_writing(lowered_task, []):
            return True

        return any(keyword in lowered_task for keyword in DOCUMENT_REFERENCE_KEYWORDS)

    def _build_confidence(self, intent_types: list[str], documents: list[PreparedDocument]) -> float:
        if intent_types == ["general"]:
            return 0.62 if not documents else 0.66
        if len(intent_types) > 1:
            return 0.9 if documents else 0.86
        return 0.84 if documents else 0.8

    def _normalize_skill_names(self, preferred_skills: list[str]) -> list[str]:
        normalized: list[str] = []
        for skill_name in preferred_skills:
            value = str(skill_name or "").strip()
            if value and value not in normalized:
                normalized.append(value)

        return normalized

    def _append_unique_skill(
        self,
        ordered_skills: list[str],
        skill_name: str,
        *,
        after_skill: str | None = None,
        before_skill: str | None = None,
    ) -> None:
        if skill_name in ordered_skills:
            return

        if before_skill and before_skill in ordered_skills:
            ordered_skills.insert(ordered_skills.index(before_skill), skill_name)
            return

        if after_skill and after_skill in ordered_skills:
            ordered_skills.insert(ordered_skills.index(after_skill) + 1, skill_name)
            return

        ordered_skills.append(skill_name)

    def _analyze_with_agent(
        self,
        *,
        task: str,
        documents: list[PreparedDocument],
        preferred_skills: list[str],
        available_skills: list[Any],
    ) -> dict[str, Any] | None:
        if self._agent_runtime is None:
            return None

        return self._agent_runtime.analyze_workflow(
            task=task,
            documents=documents,
            preferred_skills=preferred_skills,
            available_skills=available_skills,
        )

    def _normalize_available_skills(self, available_skills: Iterable[Any]) -> list[Any]:
        normalized: list[Any] = []
        for skill in available_skills:
            skill_name = str(getattr(skill, "name", "") or "").strip()
            if not skill_name:
                continue
            normalized.append(skill)

        return normalized

    def _normalize_intent_types(self, values: Any, fallback: list[str]) -> list[str]:
        if not isinstance(values, list):
            return fallback

        normalized = [value for value in values if value in DEFAULT_SKILLS_BY_INTENT]
        return normalized or fallback

    def _normalize_primary_intent(
        self,
        value: Any,
        *,
        detected_intent_types: list[str],
        fallback: str,
    ) -> str:
        if isinstance(value, str) and value in DEFAULT_SKILLS_BY_INTENT:
            return value
        return detected_intent_types[0] if detected_intent_types else fallback

    def _normalize_document_kinds(self, values: Any, fallback: list[str]) -> list[str]:
        if not isinstance(values, list):
            return fallback

        normalized = [value for value in values if value in {"invoice", "receipt", "contract", "statement", "resume", "report", "general"}]
        return normalized or fallback

    def _normalize_skill_selection(
        self,
        values: Any,
        *,
        available_skill_names: set[str],
        fallback: list[str],
        preferred_skills: list[str],
        unsupported_preferred_skills: list[str],
    ) -> list[str]:
        if not isinstance(values, list):
            return fallback

        normalized: list[str] = []
        for value in values:
            skill_name = str(value or "").strip()
            if not skill_name:
                continue
            if available_skill_names and skill_name not in available_skill_names:
                continue
            if skill_name not in normalized:
                normalized.append(skill_name)

        if not normalized:
            return fallback

        for preferred_skill in self._normalize_skill_names(preferred_skills):
            if preferred_skill in unsupported_preferred_skills:
                continue
            if preferred_skill not in normalized:
                normalized.insert(0, preferred_skill)

        return normalized

    def _normalize_bool(self, value: Any, fallback: bool) -> bool:
        if isinstance(value, bool):
            return value
        return fallback

    def _normalize_confidence(self, value: Any, fallback: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return fallback

        return min(1.0, max(0.0, confidence))

    def _normalize_notes(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []

        normalized: list[str] = []
        for value in values:
            note = str(value or "").strip()
            if note and note not in normalized:
                normalized.append(note)

        return normalized

    def _prepend_agent_mode_note(
        self,
        notes: list[str],
        *,
        agent_mode: str,
        agent_active: bool,
        agent_used: bool,
        local_fallback_enabled: bool,
    ) -> list[str]:
        prefix = ""
        if agent_mode == "off":
            prefix = "本次请求已关闭 agent，将只使用本地规则和技能。"
        elif agent_mode == "on" and agent_active:
            prefix = (
                "本次请求已显式开启 agent。"
                if agent_used
                else (
                    "本次请求已显式开启 agent，但当前环节未获取到 agent 结果，已回退到本地规则和技能。"
                    if local_fallback_enabled
                    else "本次请求已显式开启 agent，但当前环节未获取到 agent 结果。"
                )
            )
        elif agent_mode == "on" and not agent_active:
            prefix = (
                "本次请求要求启用 agent，但当前服务不可用，已回退到本地规则和技能。"
                if local_fallback_enabled
                else "本次请求要求启用 agent，但当前服务不可用。"
            )
        elif agent_mode == "auto" and not agent_active:
            prefix = (
                "当前服务未启用 agent，本次请求将使用本地规则和技能。"
                if local_fallback_enabled
                else "当前服务未启用 agent。"
            )

        if prefix:
            return [prefix, *notes]
        return notes
