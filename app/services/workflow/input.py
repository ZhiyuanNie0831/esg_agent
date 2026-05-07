"""输入标准化服务。

把上传或调用方传入的原始文档统一整理成 `PreparedDocument`，方便后续意图分析、
技能执行和最终总结使用。
"""

from app.schemas.workflow import DocumentSegment, PreparedDocument, WorkflowDocument
from app.services.workflow.segments import build_text_segments
from app.services.workflow.text_utils import merge_text_sources

PREVIEW_LIMIT = 180

DOCUMENT_KIND_KEYWORDS = {
    "invoice": ("invoice", "发票", "bill"),
    "receipt": ("receipt", "小票", "收据"),
    "contract": ("contract", "合同", "agreement", "协议"),
    "statement": ("statement", "bank", "对账", "流水"),
    "resume": ("resume", "cv", "简历"),
    "report": ("report", "报告", "summary"),
}


class WorkflowInputService:
    """在规划和执行前统一清洗输入文档。"""

    def prepare_documents(self, documents: list[WorkflowDocument]) -> list[PreparedDocument]:
        """批量生成下游统一使用的标准化文档。"""
        prepared_documents: list[PreparedDocument] = []

        for document in documents:
            ocr_text = (document.ocrText or "").strip()
            content_text = (document.contentText or "").strip()
            structured_summary = self._build_structured_summary(document)
            normalized_segments = self._normalize_segments(
                document=document,
                ocr_text=ocr_text,
                content_text=content_text,
                structured_summary=structured_summary,
            )
            normalized_text = self._build_normalized_text(
                document=document,
                ocr_text=ocr_text,
                content_text=content_text,
                structured_summary=structured_summary,
                segments=normalized_segments,
            )
            has_usable_text = bool(ocr_text or content_text or structured_summary or normalized_segments)

            prepared_documents.append(
                PreparedDocument(
                    documentId=document.documentId,
                    name=document.name,
                    type=document.type,
                    source=document.source,
                    mimeType=document.mimeType,
                    sizeBytes=document.sizeBytes,
                    parser=document.parser,
                    notes=list(document.notes),
                    text=normalized_text,
                    textPreview=self._build_preview(normalized_text),
                    hasUsableText=has_usable_text,
                    usedOcr=bool(ocr_text),
                    inferredKinds=self._infer_document_kinds(document, normalized_text),
                    segments=normalized_segments,
                    structuredData=dict(document.structuredData),
                )
            )

        return prepared_documents

    def _build_placeholder_text(self, document: WorkflowDocument) -> str:
        """为暂无可读文本的文档生成占位说明。"""
        return (
            f"[暂无可读文本] {document.name} 目前还没有可解析内容。"
            "你可以提供 contentText 或 ocrText 来模拟 OCR 或文档解析结果。"
        )

    def _build_normalized_text(
        self,
        *,
        document: WorkflowDocument,
        ocr_text: str,
        content_text: str,
        structured_summary: str,
        segments: list[DocumentSegment],
    ) -> str:
        """按优先级合并正文、OCR、结构摘要和片段文本。"""
        if content_text and ocr_text:
            return merge_text_sources(content_text, ocr_text, separator_label="OCR 补全")
        if ocr_text:
            return ocr_text
        if content_text:
            return content_text
        if structured_summary:
            return structured_summary
        if segments:
            return "\n\n".join(segment.text for segment in segments[:6]).strip()
        return self._build_placeholder_text(document)

    def _normalize_segments(
        self,
        *,
        document: WorkflowDocument,
        ocr_text: str,
        content_text: str,
        structured_summary: str,
    ) -> list[DocumentSegment]:
        """规范化文档片段；若调用方未提供片段则自动切分生成。"""
        if document.segments:
            normalized_segments: list[DocumentSegment] = []
            for index, segment in enumerate(document.segments, start=1):
                text = segment.text.strip()
                if not text:
                    continue
                normalized_segments.append(
                    segment.model_copy(
                        update={
                            "segmentId": segment.segmentId or f"segment_{index}",
                            "label": segment.label or f"片段 {index}",
                        }
                    )
                )
            return normalized_segments

        if content_text and ocr_text:
            merged_text = merge_text_sources(content_text, ocr_text, separator_label=None)
            return build_text_segments(merged_text, kind="paragraph", label_prefix="正文片段")
        if ocr_text:
            return build_text_segments(ocr_text, kind="ocr", label_prefix="OCR 片段")
        if content_text:
            return build_text_segments(content_text, kind="paragraph", label_prefix="正文片段")
        if structured_summary:
            return build_text_segments(structured_summary, kind="summary", label_prefix="结构片段")
        return []

    def _build_structured_summary(self, document: WorkflowDocument) -> str:
        """把 Excel 等结构化数据转成简短文字摘要。"""
        sheets = document.structuredData.get("sheets", [])
        if not sheets:
            return ""

        descriptions: list[str] = [f"{document.name} 已包含 {len(sheets)} 个工作表的结构化数据。"]
        for sheet in sheets[:3]:
            headers = [str(header) for header in sheet.get("headers", []) if str(header).strip()]
            row_count = int(sheet.get("rowCount", 0) or 0)
            descriptions.append(
                f"工作表 {sheet.get('title', 'Sheet')}："
                f"表头 {('、'.join(headers[:6]) if headers else '未识别')}，"
                f"共 {row_count} 行数据。"
            )

        return "\n".join(descriptions)

    def _build_preview(self, text: str) -> str:
        """生成用于列表或前端预览的短文本。"""
        compact_text = " ".join(text.split())
        if len(compact_text) <= PREVIEW_LIMIT:
            return compact_text

        return f"{compact_text[: PREVIEW_LIMIT - 1]}…"

    def _infer_document_kinds(self, document: WorkflowDocument, text: str) -> list[str]:
        """根据文件名、标签和正文内容推断文档业务类别。"""
        haystack = " ".join(
            [
                document.name.lower(),
                document.type.lower(),
                " ".join(tag.lower() for tag in document.tags),
                text.lower(),
            ]
        )
        inferred = [
            kind
            for kind, keywords in DOCUMENT_KIND_KEYWORDS.items()
            if any(keyword in haystack for keyword in keywords)
        ]
        return inferred or ["general"]
