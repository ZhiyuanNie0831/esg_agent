"""ESG 证据链接技能。"""

from app.services.workflow.esg import build_esg_evidence_links
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class ESGEvidenceLinkerSkill(WorkflowSkill):
    """把披露项、KPI 和原始材料位置连接成审计索引。"""

    name = "esg_evidence_linker"
    title = "链接 ESG 证据"
    description = "为披露主题和 KPI 建立 claim -> evidence 的索引，降低报告生成时的无依据表述风险。"
    input_hint = "ESG 主题覆盖、KPI 抽取结果和原始材料"
    output_hint = "ESG 证据链接索引"
    tags = ("esg", "evidence", "audit")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        links = build_esg_evidence_links(context.documents)
        supported_count = len([item for item in links if item.get("supportLevel") == "supported"])
        weak_count = len([item for item in links if item.get("supportLevel") == "weak"])
        evidence_refs = [
            {
                "title": str(item.get("claim") or "ESG 证据"),
                "documentId": item.get("documentId"),
                "document": str(item.get("document") or "未命名材料"),
                "location": str(item.get("location") or "正文定位未标注"),
                "excerpt": str(item.get("excerpt") or ""),
                "sourceStep": self.title,
            }
            for item in links[:6]
            if item.get("document")
        ]
        return {
            "summary": f"已建立 {len(links)} 条 ESG 证据链接，supported {supported_count} 条，weak {weak_count} 条。",
            "evidenceLinks": links,
            "linkStats": {
                "total": len(links),
                "supported": supported_count,
                "weak": weak_count,
            },
            "evidence": evidence_refs,
            "evidenceRefs": evidence_refs,
        }
