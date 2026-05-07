"""上传解析阶段使用的数据模型。"""

from dataclasses import dataclass, field

from app.schemas.workflow import DocumentSegment, WorkflowDocumentType


@dataclass(slots=True)
class ParsedUploadDocument:
    """单个文件解析器返回的统一结果结构。"""

    document_type: WorkflowDocumentType
    text: str
    parser: str
    ocr_text: str | None = None
    notes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    segments: list[DocumentSegment] = field(default_factory=list)
    structured_data: dict[str, object] = field(default_factory=dict)
