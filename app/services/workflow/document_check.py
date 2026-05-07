"""缺失材料检查服务。

负责把意图分析要求的材料类型，与当前用户已提供的文档做比对。
"""

from app.schemas.workflow import MissingDocumentCheck, PreparedDocument
from app.services.workflow.text import join_document_kind_labels


class WorkflowDocumentCheckService:
    """检查当前材料是否满足任务执行要求。"""

    def check(
        self,
        required_kinds: list[str],
        documents: list[PreparedDocument],
        document_required: bool = False,
    ) -> MissingDocumentCheck:
        """输出材料完整度、缺失项和补充建议。"""
        present_kinds = sorted({kind for document in documents for kind in document.inferredKinds})
        missing_kinds = [kind for kind in required_kinds if kind not in present_kinds]
        advice: list[str] = []

        if document_required and not documents and "general" not in missing_kinds and not required_kinds:
            missing_kinds.append("general")

        if document_required and not documents:
            advice.append("当前任务依赖待处理材料，请先上传原始文档或粘贴正文内容。")

        if missing_kinds:
            advice.append(f"建议补充这些材料：{join_document_kind_labels(missing_kinds)}。")

        unreadable_documents = [document.name for document in documents if not document.hasUsableText]
        if unreadable_documents:
            advice.append(
                f"有 {len(unreadable_documents)} 份文档暂无可读文本，建议补 OCR 或正文解析后再执行深度处理。"
            )

        if missing_kinds:
            readiness = "missing" if not documents else "partial"
        elif unreadable_documents:
            readiness = "partial"
        else:
            readiness = "ready"

        return MissingDocumentCheck(
            requiredKinds=required_kinds,
            presentKinds=present_kinds,
            missingKinds=missing_kinds,
            readiness=readiness,
            advice=advice,
            complete=not missing_kinds and (not document_required or bool(documents)),
        )
