"""OCR 服务封装。

负责调用模型 API OCR 处理图片和 PDF，并把结果转换成统一的文本与片段结构。
"""

from __future__ import annotations

import base64
import io
import logging
import re
from dataclasses import dataclass, field

from app.config import settings
from app.services.model_api import (
    ModelApiConfig,
    ModelApiFeatureUnavailableError,
    build_model_api_gateway,
)
from app.schemas.workflow import DocumentSegment
from app.services.workflow.segments import build_text_segments

IMAGE_MIME_BY_EXTENSION = {
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}
PDF_PAGE_MARKER = re.compile(r"^\[(?:第\s*(\d+)\s*页|page\s*(\d+))\]\s*$", re.IGNORECASE)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OCRExtraction:
    """单次 OCR 提取结果。"""

    text: str
    backend: str = "model_api"
    notes: list[str] = field(default_factory=list)
    segments: list[DocumentSegment] = field(default_factory=list)
    page_texts: dict[int, str] = field(default_factory=dict)


class WorkflowOCRService:
    """面向图片和 PDF 的 OCR 服务。"""

    def __init__(self) -> None:
        self._client = build_model_api_gateway(
            ModelApiConfig(
                provider=settings.model_api_ocr_provider,
                api_key=settings.model_api_ocr_key,
                base_url=settings.model_api_ocr_base_url,
                timeout_seconds=settings.model_api_ocr_timeout_seconds,
                protocol=settings.model_api_ocr_protocol,
            )
        )
        self._enabled = self._client.enabled and settings.model_api_ocr_enabled

    @property
    def enabled(self) -> bool:
        """判断 OCR 服务当前是否可用。"""
        return self._enabled and self._client is not None

    @property
    def supports_image_input(self) -> bool:
        """判断当前 OCR provider 是否支持图片输入。"""
        return bool(getattr(self._client, "supports_image_input", False))

    @property
    def supports_file_input(self) -> bool:
        """判断当前 OCR provider 是否支持文件输入。"""
        return bool(getattr(self._client, "supports_file_input", False))

    def extract_image_text(
        self,
        *,
        filename: str,
        mime_type: str | None,
        data: bytes,
    ) -> OCRExtraction | None:
        """对单张图片执行 OCR。"""
        if not self.enabled:
            return None
        if not self.supports_image_input:
            logger.info(
                "workflow image ocr skipped: provider=%s does not support image input",
                settings.model_api_ocr_provider,
            )
            return None

        image_url = self._build_image_data_url(filename=filename, mime_type=mime_type, data=data)
        response_text = self._request_text(
            input_content=[
                {
                    "type": "input_text",
                    "text": (
                        "请作为高精度 OCR 引擎，完整逐行转写图片中的所有可读文字。"
                        "不要总结，不要翻译，不要改写，不要省略。"
                        "表格尽量按行输出，印章、页眉页脚、批注附近的可读文字也要保留。"
                    ),
                },
                {
                    "type": "input_image",
                    "image_url": image_url,
                    "detail": settings.model_api_ocr_image_detail,
                },
            ],
            max_output_tokens=min(settings.model_api_ocr_max_output_tokens, 3000),
            request_label=f"image:{filename}",
        )
        if not response_text:
            return None

        cleaned_text = self._clean_response_text(response_text)
        segments = _build_ocr_segments(cleaned_text, kind="ocr", label_prefix="OCR 片段")
        return OCRExtraction(
            text=cleaned_text,
            notes=[f"已使用 {settings.model_api_ocr_provider_label} OCR 提取图片正文。"],
            segments=segments,
        )

    def extract_pdf_text(
        self,
        *,
        filename: str,
        data: bytes,
        max_pages: int | None = None,
    ) -> OCRExtraction | None:
        """对 PDF 按页执行 OCR，并尽量保留页码信息。"""
        if not self.enabled:
            return None
        if not self.supports_file_input:
            logger.info(
                "workflow pdf ocr skipped: provider=%s protocol=%s does not support inline file input",
                settings.model_api_ocr_provider,
                settings.model_api_ocr_protocol,
            )
            return None

        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            return None

        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception:
            logger.exception("workflow pdf ocr reader init failed: filename=%s", filename)
            return None
        total_pages = len(reader.pages)
        page_limit = min(total_pages, max_pages) if max_pages is not None else total_pages
        if page_limit <= 0:
            return None

        pages_per_request = max(1, settings.model_api_ocr_pdf_pages_per_request)
        page_texts: dict[int, str] = {}
        notes: list[str] = []

        for start_page in range(0, page_limit, pages_per_request):
            end_page = min(page_limit, start_page + pages_per_request)
            chunk_writer = PdfWriter()
            for page_index in range(start_page, end_page):
                chunk_writer.add_page(reader.pages[page_index])

            buffer = io.BytesIO()
            chunk_writer.write(buffer)
            response_text = self._request_text(
                input_content=[
                    {
                        "type": "input_text",
                        "text": self._build_pdf_prompt(
                            start_page=start_page + 1,
                            end_page=end_page,
                        ),
                    },
                    {
                        "type": "input_file",
                        "filename": filename,
                        "file_data": base64.b64encode(buffer.getvalue()).decode("utf-8"),
                    },
                ],
                max_output_tokens=self._estimate_pdf_output_tokens(end_page - start_page),
                request_label=f"pdf:{filename}:{start_page + 1}-{end_page}",
            )
            if not response_text:
                notes.append(f"第 {start_page + 1}-{end_page} 页 OCR 未返回结果。")
                continue

            parsed_pages = self._parse_pdf_chunk_text(
                text=response_text,
                start_page=start_page + 1,
                end_page=end_page,
            )
            if not parsed_pages:
                if start_page + 1 != end_page:
                    notes.append(
                        f"第 {start_page + 1}-{end_page} 页 OCR 输出未按页标记，已回退为逐页重试。"
                    )
                    retried_pages = self._retry_pdf_pages_individually(
                        filename=filename,
                        reader=reader,
                        start_page=start_page + 1,
                        end_page=end_page,
                    )
                    if retried_pages:
                        parsed_pages = retried_pages
                        notes.append(
                            f"第 {start_page + 1}-{end_page} 页逐页重试成功返回 {len(retried_pages)} 页文本。"
                        )
                if not parsed_pages:
                    notes.append(
                        f"第 {start_page + 1}-{end_page} 页 OCR 输出仍无法按页拆分，已按整块保留到起始页。"
                    )
                    parsed_pages = {start_page + 1: self._clean_response_text(response_text)}

            for page_number, page_text in parsed_pages.items():
                cleaned_page_text = self._clean_response_text(page_text)
                if cleaned_page_text:
                    page_texts[page_number] = cleaned_page_text

        if not page_texts:
            return None

        ordered_pages = sorted(page_texts)
        combined_text = "\n\n".join(
            f"[第 {page_number} 页]\n{page_texts[page_number]}" for page_number in ordered_pages
        )
        segments = _build_pdf_ocr_segments(page_texts)
        notes.insert(0, f"已使用 {settings.model_api_ocr_provider_label} OCR 逐页补全文档，共返回 {len(page_texts)} 页文本。")
        return OCRExtraction(
            text=combined_text,
            notes=notes,
            segments=segments,
            page_texts=page_texts,
        )

    def _request_text(
        self,
        *,
        input_content: list[dict[str, object]],
        max_output_tokens: int,
        request_label: str,
    ) -> str | None:
        """请求 OCR 文本结果。"""
        if not self._client.enabled:
            return None

        try:
            text = self._client.request_text(
                model=settings.model_api_ocr_model,
                instructions=(
                    "你是一个高精度 OCR 引擎。"
                    "只输出可读正文，不要总结，不要解释，不要添加提示语。"
                ),
                input_payload=[{"role": "user", "content": input_content}],
                max_output_tokens=max_output_tokens,
                temperature=0,
            )
        except ModelApiFeatureUnavailableError:
            logger.info(
                "workflow ocr request skipped due to provider capability: provider=%s request=%s",
                settings.model_api_ocr_provider,
                request_label,
            )
            return None
        except Exception:
            logger.exception(
                "workflow ocr request failed: provider=%s request=%s model=%s max_output_tokens=%s",
                settings.model_api_ocr_provider,
                request_label,
                settings.model_api_ocr_model,
                max_output_tokens,
            )
            return None

        if not text:
            logger.warning(
                "workflow ocr returned empty output: provider=%s request=%s model=%s",
                settings.model_api_ocr_provider,
                request_label,
                settings.model_api_ocr_model,
            )
        return text or None

    def _build_image_data_url(self, *, filename: str, mime_type: str | None, data: bytes) -> str:
        """把图片字节封装成 data URL，供 OCR 接口调用。"""
        resolved_mime = (mime_type or "").strip() or IMAGE_MIME_BY_EXTENSION.get(
            self._suffix_from_filename(filename),
            "image/png",
        )
        encoded = base64.b64encode(data).decode("utf-8")
        return f"data:{resolved_mime};base64,{encoded}"

    def _build_pdf_prompt(self, *, start_page: int, end_page: int) -> str:
        """根据页范围生成 PDF OCR 提示词。"""
        if start_page == end_page:
            return (
                f"请对这个 PDF 的第 {start_page} 页做完整 OCR 转写。"
                "不要总结，不要翻译，不要改写，不要省略。"
                "只输出该页正文内容。"
            )

        page_templates = "\n".join(
            f"[第 {page_number} 页]\n<该页正文>"
            for page_number in range(start_page, end_page + 1)
        )
        return (
            f"请对这个 PDF 的第 {start_page} 页到第 {end_page} 页做完整 OCR 转写。"
            "不要总结，不要翻译，不要改写，不要省略。"
            "必须严格按如下格式逐页输出，每一页都要带页码标记：\n"
            f"{page_templates}\n"
            "页与页之间不要合并，不要漏页，也不要添加额外说明。"
        )

    def _retry_pdf_pages_individually(
        self,
        *,
        filename: str,
        reader,
        start_page: int,
        end_page: int,
    ) -> dict[int, str]:
        """当多页 OCR 输出不稳定时，退回到逐页请求，尽量保住页码映射。"""
        try:
            from pypdf import PdfWriter
        except ImportError:
            return {}

        retried_pages: dict[int, str] = {}
        for page_number in range(start_page, end_page + 1):
            page_writer = PdfWriter()
            page_writer.add_page(reader.pages[page_number - 1])
            page_buffer = io.BytesIO()
            page_writer.write(page_buffer)
            response_text = self._request_text(
                input_content=[
                    {
                        "type": "input_text",
                        "text": self._build_pdf_prompt(
                            start_page=page_number,
                            end_page=page_number,
                        ),
                    },
                    {
                        "type": "input_file",
                        "filename": filename,
                        "file_data": base64.b64encode(page_buffer.getvalue()).decode("utf-8"),
                    },
                ],
                max_output_tokens=self._estimate_pdf_output_tokens(1),
                request_label=f"pdf:{filename}:retry:{page_number}",
            )
            cleaned_text = self._clean_response_text(response_text or "")
            if cleaned_text:
                retried_pages[page_number] = cleaned_text

        return retried_pages

    def _parse_pdf_chunk_text(
        self,
        *,
        text: str,
        start_page: int,
        end_page: int,
    ) -> dict[int, str]:
        """把多页 OCR 返回文本拆解成“页码 -> 页内容”映射。"""
        cleaned_text = self._clean_response_text(text)
        if start_page == end_page:
            return {start_page: cleaned_text} if cleaned_text else {}

        page_texts: dict[int, str] = {}
        current_page: int | None = None
        current_lines: list[str] = []

        for line in cleaned_text.splitlines():
            marker = PDF_PAGE_MARKER.match(line.strip())
            if marker:
                if current_page is not None:
                    page_texts[current_page] = "\n".join(current_lines).strip()
                current_page = int(marker.group(1) or marker.group(2))
                current_lines = []
                continue
            current_lines.append(line)

        if current_page is not None:
            page_texts[current_page] = "\n".join(current_lines).strip()

        expected_pages = set(range(start_page, end_page + 1))
        if not expected_pages.issubset(page_texts):
            return {}

        return {page: page_texts[page] for page in sorted(expected_pages)}

    def _estimate_pdf_output_tokens(self, page_count: int) -> int:
        requested_tokens = max(2000, page_count * 2200)
        return min(settings.model_api_ocr_max_output_tokens, requested_tokens)

    def _clean_response_text(self, text: str) -> str:
        stripped = str(text or "").strip()
        if stripped.startswith("```"):
            lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
            stripped = "\n".join(lines).strip()
        return stripped

    def _suffix_from_filename(self, filename: str) -> str:
        if "." not in filename:
            return ""
        return f".{filename.rsplit('.', 1)[-1].lower()}"


def _build_ocr_segments(text: str, *, kind: str, label_prefix: str) -> list[DocumentSegment]:
    segments = build_text_segments(text, kind=kind, label_prefix=label_prefix)
    return [
        segment.model_copy(update={"segmentId": f"{kind}_{index}"})
        for index, segment in enumerate(segments, start=1)
    ]


def _build_pdf_ocr_segments(page_texts: dict[int, str]) -> list[DocumentSegment]:
    segments: list[DocumentSegment] = []
    for page_number in sorted(page_texts):
        built_segments = build_text_segments(
            page_texts[page_number],
            kind="ocr",
            label_prefix=f"OCR 第 {page_number} 页",
            page=page_number,
        )
        for segment_index, segment in enumerate(built_segments, start=1):
            segments.append(
                segment.model_copy(update={"segmentId": f"ocr_page_{page_number}_{segment_index}"})
            )
    return segments


workflow_ocr_service = WorkflowOCRService()
