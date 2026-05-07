"""证据工具函数。

负责把文档片段、人工整理结论等内容统一转换成前端可展示的证据项。
"""

from __future__ import annotations

from app.schemas.workflow import DocumentSegment, PreparedDocument, WorkflowEvidenceItem

EXCERPT_LIMIT = 220


def clip_excerpt(text: str, *, limit: int = EXCERPT_LIMIT) -> str:
    """裁剪证据摘录，避免文本过长。"""
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"


def format_segment_location(segment: DocumentSegment) -> str:
    """把片段的页码、章节、sheet、行号等信息格式化成人可读位置。"""
    parts: list[str] = []
    if segment.page is not None:
        parts.append(f"第 {segment.page} 页")
    if segment.section:
        parts.append(f"章节 {segment.section}")
    if segment.sheet:
        parts.append(f"工作表 {segment.sheet}")
    if segment.rowStart is not None and segment.rowEnd is not None and segment.rowEnd != segment.rowStart:
        parts.append(f"第 {segment.rowStart}-{segment.rowEnd} 行")
    elif segment.rowStart is not None:
        parts.append(f"第 {segment.rowStart} 行")
    if segment.label:
        parts.append(segment.label)
    return " / ".join(parts) or "正文定位未标注"


def build_segment_evidence(
    *,
    title: str,
    document_id: str | None,
    document_name: str,
    segment: DocumentSegment,
    source_step: str | None = None,
    excerpt: str | None = None,
    cell_range: str | None = None,
) -> dict[str, str]:
    """由文档片段生成一条证据项。"""
    return WorkflowEvidenceItem(
        title=title,
        documentId=document_id,
        document=document_name,
        location=format_segment_location(segment),
        excerpt=clip_excerpt(excerpt if excerpt is not None else segment.text),
        sourceStep=source_step,
        segmentId=segment.segmentId,
        page=segment.page,
        section=segment.section,
        sheet=segment.sheet,
        rowStart=segment.rowStart,
        rowEnd=segment.rowEnd,
        cellRange=cell_range,
    ).model_dump()


def build_manual_evidence(
    *,
    title: str,
    document_id: str | None,
    document_name: str,
    location: str,
    excerpt: str,
    source_step: str | None = None,
    page: int | None = None,
    section: str | None = None,
    sheet: str | None = None,
    row_start: int | None = None,
    row_end: int | None = None,
    cell_range: str | None = None,
) -> dict[str, str]:
    """由手工提供的位置和摘录生成一条证据项。"""
    return WorkflowEvidenceItem(
        title=title,
        documentId=document_id,
        document=document_name,
        location=location or "正文定位未标注",
        excerpt=clip_excerpt(excerpt),
        sourceStep=source_step,
        page=page,
        section=section,
        sheet=sheet,
        rowStart=row_start,
        rowEnd=row_end,
        cellRange=cell_range,
    ).model_dump()


def collect_document_evidence(
    documents: list[PreparedDocument],
    *,
    max_items: int = 4,
    source_step: str | None = None,
) -> list[dict[str, str]]:
    """从文档列表里抽取一批默认展示证据。"""
    items: list[dict[str, str]] = []

    for document in documents:
        if len(items) >= max_items:
            break

        segments = [segment for segment in document.segments if segment.text.strip()]
        if segments:
            items.append(
                build_segment_evidence(
                    title=document.name,
                    document_id=document.documentId,
                    document_name=document.name,
                    segment=segments[0],
                    source_step=source_step,
                )
            )
            continue

        items.append(
            build_manual_evidence(
                title=document.name,
                document_id=document.documentId,
                document_name=document.name,
                location="正文摘要",
                excerpt=document.textPreview or document.text,
                source_step=source_step,
            )
        )

    return items
