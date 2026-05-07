"""ESG 报告正文生成技能。"""

from __future__ import annotations

import base64
from typing import Any

from app.services.workflow.esg import (
    PILLAR_LABELS,
    build_esg_disclosure_matrix,
    build_esg_evidence_links,
    build_esg_outline,
    estimate_report_word_count,
    extract_esg_indicators,
    resolve_esg_report_word_count,
    select_esg_standards,
)
from app.services.workflow.evidence import collect_document_evidence
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class ESGReportWriterSkill(WorkflowSkill):
    """根据上传材料生成 ESG 报告正文。"""

    name = "esg_report_writer"
    title = "生成 ESG 报告"
    description = "根据上传材料、披露矩阵、KPI 和证据索引生成指定字数的 ESG 报告草稿。"
    input_hint = "ESG 材料、标准选择、披露矩阵、KPI、证据链接和客户字数要求"
    output_hint = "ESG 报告 Markdown 正文和可下载草稿"
    requires_approval = True
    tags = ("esg", "report", "write")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        """生成报告正文，优先使用 agent，失败时回退到本地规则草稿。"""
        documents, document_context = context.build_document_context(
            max_documents=12,
            max_segments_per_document=8,
            max_total_segments=48,
            segment_text_limit=900,
        )
        requirements = resolve_esg_report_word_count(context.task)
        report_context = self._build_report_context(
            task=context.task,
            documents=documents,
            previous_results=context.previous_results,
            document_context=document_context,
            requirements=requirements,
        )

        report_markdown = ""
        source = "local_skill"
        writer = getattr(context.agent_runtime, "write_esg_report", None) if context.agent_runtime else None
        if callable(writer):
            report_markdown = writer(
                task=context.task,
                documents=documents,
                report_context=report_context,
                requirements=requirements,
            ) or ""
            if report_markdown.strip():
                source = "agent"

        if not report_markdown.strip():
            context.require_local_fallback("ESG 报告生成")
            report_markdown = self._build_local_report(report_context)

        estimated_word_count = estimate_report_word_count(report_markdown)
        evidence_refs = self._build_evidence_refs(report_context)
        export_files = [
            {
                "label": "ESG 报告草稿",
                "filename": "esg_report_draft.md",
                "mimeType": "text/markdown; charset=utf-8",
                "contentBase64": base64.b64encode(report_markdown.encode("utf-8")).decode("ascii"),
            }
        ]
        summary = (
            "已根据上传材料生成 ESG 报告草稿。"
            f"客户字数要求：{requirements['description']}；"
            f"当前估算字数：{estimated_word_count}。"
        )
        if not requirements["explicit"]:
            summary += "如需严格控制篇幅，请在任务中明确目标字数后重跑。"

        return {
            "summary": summary,
            "source": source,
            "reportMarkdown": report_markdown,
            "revisedDocument": report_markdown,
            "targetWordCount": requirements["targetWordCount"],
            "minWordCount": requirements["minWordCount"],
            "maxWordCount": requirements["maxWordCount"],
            "estimatedWordCount": estimated_word_count,
            "wordCountRequirement": requirements,
            "standards": report_context["standards"],
            "disclosureMatrix": report_context["disclosureMatrix"],
            "matrixStats": report_context["matrixStats"],
            "indicators": report_context["indicators"],
            "evidenceLinks": report_context["evidenceLinks"],
            "exportFiles": export_files,
            "evidence": evidence_refs,
            "evidenceRefs": evidence_refs,
        }

    def _build_report_context(
        self,
        *,
        task: str,
        documents: list[Any],
        previous_results: dict[str, dict[str, Any]],
        document_context: dict[str, Any],
        requirements: dict[str, Any],
    ) -> dict[str, Any]:
        standard_result = previous_results.get("esg_standard_selector", {})
        standards = standard_result.get("standards")
        if not isinstance(standards, list) or not standards:
            standards = select_esg_standards(task, documents)["standards"]

        matrix_result = previous_results.get("esg_disclosure_matrix_builder", {})
        disclosure_matrix = matrix_result.get("disclosureMatrix")
        matrix_stats = matrix_result.get("matrixStats")
        if not isinstance(disclosure_matrix, list) or not isinstance(matrix_stats, dict):
            matrix_bundle = build_esg_disclosure_matrix(documents, standards=standards)
            disclosure_matrix = matrix_bundle["matrix"]
            matrix_stats = matrix_bundle["stats"]

        indicator_result = previous_results.get("esg_kpi_extractor", {})
        indicators = indicator_result.get("indicators")
        if not isinstance(indicators, list):
            indicators = extract_esg_indicators(documents)

        evidence_result = previous_results.get("esg_evidence_linker", {})
        evidence_links = evidence_result.get("evidenceLinks")
        if not isinstance(evidence_links, list):
            evidence_links = build_esg_evidence_links(documents)

        outline_result = previous_results.get("esg_report_outline_builder", {})
        outline_markdown = str(outline_result.get("outlineMarkdown") or "").strip()
        if not outline_markdown:
            outline_markdown = build_esg_outline(documents)["outlineMarkdown"]

        return {
            "task": task,
            "requirements": requirements,
            "documentContext": document_context,
            "documentEvidence": collect_document_evidence(documents, source_step=self.title),
            "standards": standards,
            "disclosureMatrix": disclosure_matrix,
            "matrixStats": matrix_stats,
            "indicators": indicators,
            "evidenceLinks": evidence_links,
            "outlineMarkdown": outline_markdown,
        }

    def _build_local_report(self, report_context: dict[str, Any]) -> str:
        requirements = report_context["requirements"]
        standards = report_context["standards"]
        matrix_items = report_context["disclosureMatrix"]
        matrix_stats = report_context["matrixStats"]
        indicators = report_context["indicators"]
        evidence_links = report_context["evidenceLinks"]

        standard_line = "、".join(
            str(item.get("code") or item.get("name") or "").strip()
            for item in standards
            if isinstance(item, dict) and str(item.get("code") or item.get("name") or "").strip()
        ) or "GRI"
        sections = [
            "# ESG 报告草稿",
            "",
            "## 报告说明",
            (
                f"本报告草稿根据已上传材料自动生成，目标篇幅为{requirements['description']}。"
                f"当前披露基础参考 {standard_line}。"
                "对于材料中未出现或证据不足的信息，正文以“待补充”方式保留，不做事实编造。"
            ),
            "",
            "## 管理层摘要",
            (
                "本期 ESG 披露材料已经覆盖环境、社会和治理三个维度中的部分主题。"
                f"披露矩阵显示 covered {matrix_stats.get('covered', 0)} 项、"
                f"weak {matrix_stats.get('weak', 0)} 项、missing {matrix_stats.get('missing', 0)} 项。"
                "报告正式发布前，应优先补强 weak 和 missing 项的量化数据、统计口径和责任部门确认记录。"
            ),
        ]
        if indicators:
            indicator_line = "；".join(
                f"{self._display_value(item.get('metric'))} {self._display_value(item.get('value'))}{self._display_value(item.get('unit'), fallback='')}"
                for item in indicators[:6]
            )
            sections.append(f"当前材料可直接引用的关键指标包括：{indicator_line}。")
        else:
            sections.append("当前材料中可直接引用的量化 KPI 较少，建议补充完整指标台账。")

        for pillar in ("environment", "social", "governance"):
            sections.extend(self._build_pillar_section(pillar, matrix_items, evidence_links))

        sections.extend(self._build_indicator_section(indicators))
        sections.extend(self._build_gap_section(matrix_items))
        sections.extend(self._build_evidence_section(evidence_links))
        return "\n".join(sections).strip()

    def _build_pillar_section(
        self,
        pillar: str,
        matrix_items: list[dict[str, Any]],
        evidence_links: list[dict[str, Any]],
    ) -> list[str]:
        pillar_label = PILLAR_LABELS[pillar]
        topics = [item for item in matrix_items if item.get("pillar") == pillar]
        lines = ["", f"## {pillar_label}"]
        if not topics:
            lines.append(f"当前材料中暂未形成稳定的{pillar_label}主题证据，建议补充相关政策、行动和 KPI。")
            return lines

        for topic in topics[:8]:
            status = str(topic.get("status") or "missing")
            topic_name = str(topic.get("topic") or "未命名主题")
            next_action = str(topic.get("nextAction") or "")
            evidence = self._find_topic_evidence(topic_name, evidence_links)
            if status == "covered":
                lines.append(f"### {topic_name}")
                lines.append(
                    "已上传材料对该主题提供了基础证据。"
                    f"{'相关证据显示：' + evidence if evidence else '建议在正式报告中补充更完整的年度进展。'}"
                )
            elif status == "weak":
                lines.append(f"### {topic_name}")
                lines.append(
                    "该主题已有初步证据，但证据数量或量化口径仍偏弱。"
                    f"{next_action or '建议补充管理措施、年度数据和边界说明。'}"
                )
            else:
                lines.append(f"### {topic_name}")
                lines.append(
                    "当前材料尚未充分覆盖该主题。"
                    f"{next_action or '正式报告中应标记为待补充，并向责任部门追要数据。'}"
                )
        return lines

    def _build_indicator_section(self, indicators: list[dict[str, Any]]) -> list[str]:
        lines = ["", "## 关键绩效指标"]
        if not indicators:
            lines.append("当前材料中尚未识别到可直接披露的 ESG KPI。")
            return lines

        lines.extend([
            "| 指标 | 数值 | 单位 | 来源 |",
            "| --- | ---: | --- | --- |",
        ])
        for item in indicators[:12]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(item.get("metric") or "-"),
                        self._display_value(item.get("value")),
                        self._display_value(item.get("unit")),
                        f"{item.get('sourceDocument') or '-'} / {item.get('sourceLocation') or '-'}",
                    ]
                )
                + " |"
            )
        return lines

    def _build_gap_section(self, matrix_items: list[dict[str, Any]]) -> list[str]:
        gaps = [item for item in matrix_items if item.get("status") in {"weak", "missing"}]
        lines = ["", "## 数据缺口与后续动作"]
        if not gaps:
            lines.append("当前矩阵未识别出明显缺口。正式发布前仍建议进行数据口径、边界和审批记录复核。")
            return lines
        for item in gaps[:10]:
            lines.append(
                f"- {item.get('topic') or '未命名主题'}："
                f"{item.get('nextAction') or '补充年度数据、管理措施和来源文件。'}"
            )
        return lines

    def _build_evidence_section(self, evidence_links: list[dict[str, Any]]) -> list[str]:
        lines = ["", "## 证据索引"]
        if not evidence_links:
            lines.append("当前没有形成稳定证据索引。")
            return lines
        for item in evidence_links[:8]:
            lines.append(
                f"- {item.get('claim') or 'ESG 证据'}："
                f"{item.get('document') or '-'} / {item.get('location') or '-'}。"
            )
        return lines

    def _find_topic_evidence(self, topic_name: str, evidence_links: list[dict[str, Any]]) -> str:
        for item in evidence_links:
            claim = str(item.get("claim") or "")
            if topic_name and topic_name in claim:
                excerpt = str(item.get("excerpt") or "").strip()
                return excerpt[:160]
        return ""

    def _build_evidence_refs(self, report_context: dict[str, Any]) -> list[dict[str, Any]]:
        refs = []
        for item in report_context.get("evidenceLinks", [])[:8]:
            if not isinstance(item, dict) or not item.get("document"):
                continue
            refs.append(
                {
                    "title": str(item.get("claim") or "ESG 报告证据"),
                    "documentId": item.get("documentId"),
                    "document": str(item.get("document") or "未命名材料"),
                    "location": str(item.get("location") or "正文定位未标注"),
                    "excerpt": str(item.get("excerpt") or ""),
                    "sourceStep": self.title,
                }
            )
        if refs:
            return refs
        evidence = report_context.get("documentEvidence", [])
        return evidence if isinstance(evidence, list) else []

    def _display_value(self, value: object, *, fallback: str = "-") -> str:
        if value is None:
            return fallback
        text = str(value).strip()
        return text if text else fallback
