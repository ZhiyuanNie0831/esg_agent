"""文档片段处理工具。

负责文本切片、任务关键词提取，以及为 agent/技能挑选更相关的文档片段。
"""

from __future__ import annotations

import re
from typing import Any

from app.schemas.workflow import DocumentSegment, PreparedDocument

DEFAULT_SEGMENT_CHAR_LIMIT = 900
DEFAULT_SEGMENT_OVERLAP = 120
TASK_STOPWORDS = {
    "请",
    "帮我",
    "我们",
    "你",
    "需要",
    "内容",
    "材料",
    "文档",
    "文件",
    "附件",
    "输出",
    "整理",
    "说明",
    "版本",
    "about",
    "this",
    "that",
    "with",
    "from",
    "into",
    "please",
    "help",
    "document",
    "documents",
    "file",
    "files",
}


def build_text_segments(
    text: str,
    *,
    kind: str = "paragraph",
    label_prefix: str = "片段",
    max_segment_chars: int = DEFAULT_SEGMENT_CHAR_LIMIT,
    page: int | None = None,
    section: str | None = None,
    sheet: str | None = None,
    row_start: int | None = None,
    row_end: int | None = None,
) -> list[DocumentSegment]:
    """把长文本切分成带来源信息的片段列表。"""
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return []

    blocks = _split_text_blocks(normalized_text)
    segments: list[DocumentSegment] = []
    for block in blocks:
        for chunk in _chunk_text_block(block, max_segment_chars=max_segment_chars):
            index = len(segments) + 1
            segments.append(
                DocumentSegment(
                    segmentId=f"{kind}_{index}",
                    kind=kind,
                    label=f"{label_prefix} {index}",
                    text=chunk,
                    page=page,
                    section=section,
                    sheet=sheet,
                    rowStart=row_start,
                    rowEnd=row_end,
                )
            )

    return segments


def serialize_documents_for_task(
    task: str,
    documents: list[PreparedDocument],
    *,
    max_documents: int,
    max_segments_per_document: int,
    max_total_segments: int,
    segment_text_limit: int,
) -> dict[str, Any]:
    """为当前任务挑选最相关的文档和片段，供 agent 使用。"""
    task_keywords, ranked_documents = _prepare_ranked_documents(task, documents)
    selected_documents: list[dict[str, Any]] = []
    remaining_segments = max_total_segments

    for item in ranked_documents[:max_documents]:
        if remaining_segments <= 0:
            break

        chosen_segments = item["selectedSegments"][: min(max_segments_per_document, remaining_segments)]
        remaining_segments -= len(chosen_segments)
        selected_documents.append(
            _serialize_selected_document(item, chosen_segments, segment_text_limit)
        )

    return {
        "taskKeywords": task_keywords[:12],
        "selectedSegmentCount": max_total_segments - remaining_segments,
        "documents": selected_documents,
    }


def select_documents_for_task(
    task: str,
    documents: list[PreparedDocument],
    *,
    max_documents: int | None = None,
    allowed_types: set[str] | None = None,
) -> list[PreparedDocument]:
    """返回与当前任务更相关的文档子集。

    当任务关键词已经命中部分文档时，只保留这些命中文档，避免多文件场景把无关材料一起送入后续技能。
    如果任务本身过于泛化、暂时没有命中结果，则回退到原始排序后的文档列表。
    """
    _, ranked_documents = _prepare_ranked_documents(
        task,
        documents,
        allowed_types=allowed_types,
    )
    if max_documents is not None:
        ranked_documents = ranked_documents[:max_documents]
    return [item["document"] for item in ranked_documents]


def extract_task_keywords(task: str) -> list[str]:
    """从任务描述中提取用于匹配文档的关键词。"""
    lowered = str(task or "").lower()
    raw_tokens = re.findall(r"[a-z0-9][a-z0-9_/-]{1,}|[\u4e00-\u9fff]{2,}", lowered)
    keywords: list[str] = []

    for token in raw_tokens:
        normalized = token.strip("-_/")
        if not normalized:
            continue

        candidates = _expand_task_token(normalized)
        for candidate in candidates:
            if not candidate or candidate in TASK_STOPWORDS:
                continue
            if candidate in keywords:
                continue
            keywords.append(candidate)

    return keywords


def _expand_task_token(token: str) -> list[str]:
    """扩展中文长词，便于提高匹配召回率。"""
    if re.fullmatch(r"[\u4e00-\u9fff]+", token):
        if len(token) <= 2:
            return [token]

        expanded: list[str] = []
        for index in range(0, len(token) - 1):
            expanded.append(token[index : index + 2])
        if len(token) <= 4:
            expanded.append(token)
        return expanded

    return [token]


def _prepare_ranked_documents(
    task: str,
    documents: list[PreparedDocument],
    *,
    allowed_types: set[str] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """提取任务关键词并返回排序后的文档。"""
    task_keywords = extract_task_keywords(task)
    ranked_documents = _rank_documents_for_task(
        task_keywords,
        documents,
        allowed_types=allowed_types,
    )
    return task_keywords, ranked_documents


def _rank_document_for_task(
    document: PreparedDocument,
    task_keywords: list[str],
    document_index: int,
) -> dict[str, Any]:
    """为单份文档打分，并挑出最相关的片段。"""
    segments = list(document.segments)
    if not segments:
        segments = build_text_segments(
            document.text,
            kind="document",
            label_prefix="正文片段",
        )

    scored_segments = []
    for index, segment in enumerate(segments):
        score, matched_keywords = _score_segment(document, segment, task_keywords, index)
        scored_segments.append((score, index, segment, matched_keywords))

    if task_keywords and any(matched_keywords for *_, matched_keywords in scored_segments):
        scored_segments = [item for item in scored_segments if item[3]]

    scored_segments.sort(key=lambda item: (-item[0], item[1]))
    if not scored_segments:
        scored_segments = [
            (1.0, index, segment, [])
            for index, segment in enumerate(segments[:2])
        ]

    selected_segments = [
        (segment, matched_keywords)
        for _, _, segment, matched_keywords in scored_segments
    ]
    document_score = scored_segments[0][0] if scored_segments else 0.0
    document_matched_keywords = list(
        dict.fromkeys(
            keyword
            for _, _, _, matched_keywords in scored_segments
            for keyword in matched_keywords
        )
    )
    return {
        "document": document,
        "documentIndex": document_index,
        "documentScore": document_score,
        "matchedKeywords": document_matched_keywords,
        "matchedKeywordCount": len(document_matched_keywords),
        "selectedSegments": selected_segments,
    }


def _rank_documents_for_task(
    task_keywords: list[str],
    documents: list[PreparedDocument],
    *,
    allowed_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    """按任务相关度为文档排序，并在有命中时剔除无关文档。"""
    allowed_type_set = {document_type.lower() for document_type in allowed_types or set()}
    ranked_documents = [
        _rank_document_for_task(document, task_keywords, document_index)
        for document_index, document in enumerate(documents)
        if not allowed_type_set or document.type.lower() in allowed_type_set
    ]
    ranked_documents.sort(
        key=lambda item: (
            -item["matchedKeywordCount"],
            -item["documentScore"],
            item["documentIndex"],
        )
    )
    if task_keywords and any(item["matchedKeywordCount"] > 0 for item in ranked_documents):
        ranked_documents = [item for item in ranked_documents if item["matchedKeywordCount"] > 0]
    return ranked_documents


def _serialize_selected_document(
    item: dict[str, Any],
    chosen_segments: list[tuple[DocumentSegment, list[str]]],
    segment_text_limit: int,
) -> dict[str, Any]:
    """把排序后的文档结果整理成返回结构。"""
    document = item["document"]
    return {
        "name": document.name,
        "type": document.type,
        "parser": document.parser,
        "inferredKinds": list(document.inferredKinds),
        "textPreview": document.textPreview,
        "hasUsableText": document.hasUsableText,
        "usedOcr": document.usedOcr,
        "segmentCount": len(document.segments),
        "selectedSegments": [
            _serialize_segment(segment, matched_keywords, segment_text_limit)
            for segment, matched_keywords in chosen_segments
        ],
    }


def _score_segment(
    document: PreparedDocument,
    segment: DocumentSegment,
    task_keywords: list[str],
    segment_index: int,
) -> tuple[float, list[str]]:
    """计算某个片段与当前任务的相关度分数。"""
    segment_haystack = " ".join(
        value
        for value in (
            segment.label,
            segment.section,
            segment.sheet,
            segment.text,
        )
        if value
    ).lower()
    document_haystack = " ".join(
        [
            document.name.lower(),
            document.type.lower(),
            " ".join(document.inferredKinds).lower(),
        ]
    )
    matched_keywords: list[str] = []
    score = max(0.1, 1.8 - segment_index * 0.08)

    for keyword in task_keywords:
        if keyword in segment_haystack:
            score += 4.0 + min(segment_haystack.count(keyword), 2)
            if keyword not in matched_keywords:
                matched_keywords.append(keyword)
        elif keyword in document_haystack:
            score += 1.0

    if segment.page is not None:
        score += 0.2
    if segment.sheet:
        score += 0.4
    if segment.rowStart is not None:
        score += 0.3

    return score, matched_keywords


def _serialize_segment(
    segment: DocumentSegment,
    matched_keywords: list[str],
    segment_text_limit: int,
) -> dict[str, Any]:
    """把片段对象转换成可序列化结构。"""
    return {
        "segmentId": segment.segmentId,
        "kind": segment.kind,
        "label": segment.label,
        "page": segment.page,
        "section": segment.section,
        "sheet": segment.sheet,
        "rowStart": segment.rowStart,
        "rowEnd": segment.rowEnd,
        "matchedKeywords": matched_keywords,
        "text": _clip_text(segment.text, segment_text_limit),
    }


def _split_text_blocks(text: str) -> list[str]:
    paragraph_blocks = [block.strip() for block in re.split(r"\n\s*\n+", text) if block.strip()]
    if len(paragraph_blocks) > 1:
        return paragraph_blocks

    line_blocks = [line.strip() for line in text.splitlines() if line.strip()]
    if len(line_blocks) > 1:
        return line_blocks

    sentence_blocks = [part.strip() for part in re.split(r"(?<=[。！？!?；;])\s*", text) if part.strip()]
    return sentence_blocks or [text]


def _chunk_text_block(text: str, *, max_segment_chars: int) -> list[str]:
    normalized = text.strip()
    if len(normalized) <= max_segment_chars:
        return [normalized]

    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?；;])\s*", normalized) if part.strip()]
    if len(sentences) <= 1:
        return _slice_text_with_overlap(normalized, max_segment_chars=max_segment_chars)

    chunks: list[str] = []
    current_lines: list[str] = []
    current_length = 0
    for sentence in sentences:
        sentence_length = len(sentence)
        if current_lines and current_length + sentence_length + 1 > max_segment_chars:
            chunks.append(" ".join(current_lines).strip())
            current_lines = [sentence]
            current_length = sentence_length
            continue

        current_lines.append(sentence)
        current_length += sentence_length + 1

    if current_lines:
        chunks.append(" ".join(current_lines).strip())

    return chunks or _slice_text_with_overlap(normalized, max_segment_chars=max_segment_chars)


def _slice_text_with_overlap(text: str, *, max_segment_chars: int) -> list[str]:
    if len(text) <= max_segment_chars:
        return [text]

    step = max(200, max_segment_chars - DEFAULT_SEGMENT_OVERLAP)
    chunks: list[str] = []
    for start in range(0, len(text), step):
        chunk = text[start : start + max_segment_chars].strip()
        if chunk:
            chunks.append(chunk)
        if start + max_segment_chars >= len(text):
            break

    return chunks


def _clip_text(text: str, limit: int) -> str:
    compact_text = str(text or "").strip()
    if len(compact_text) <= limit:
        return compact_text
    return compact_text[: limit - 1] + "…"
