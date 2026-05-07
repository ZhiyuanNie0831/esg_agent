"""上传服务。

负责接收用户文件，调用解析器，并把结果包装成统一工作流文档结构。
"""

from __future__ import annotations

from fastapi import UploadFile

from app.schemas.workflow import WorkflowDocument, WorkflowUploadResponse
from app.services.workflow.session_store import workflow_session_store
from app.services.workflow.uploads.parsers import parse_uploaded_bytes
from app.services.workflow.uploads.store import workflow_upload_store


class WorkflowUploadService:
    """接收上传文件并转换成工作流文档。"""

    async def upload(
        self,
        files: list[UploadFile],
        *,
        session_id: str | None = None,
    ) -> WorkflowUploadResponse:
        """批量解析上传文件，返回文档列表和警告信息。"""
        documents: list[WorkflowDocument] = []
        warnings: list[str] = []

        for file in files:
            filename = file.filename or "untitled"
            file_bytes = await file.read()
            try:
                parsed = parse_uploaded_bytes(
                    filename=filename,
                    content_type=file.content_type,
                    data=file_bytes,
                )
            except Exception as exc:
                parsed = WorkflowDocument(
                    name=filename,
                    type="other",
                    source="upload",
                    mimeType=file.content_type,
                    sizeBytes=len(file_bytes),
                    parser="upload_error",
                    notes=[f"读取失败：{exc}"],
                    contentText=f"[读取失败] {filename} 当前无法解析，请检查文件内容或补充专用 parser。",
                )
                documents.append(parsed)
                warnings.append(f"{filename}: 读取失败：{exc}")
                await file.close()
                continue

            documents.append(
                WorkflowDocument(
                    name=filename,
                    type=parsed.document_type,
                    source="upload",
                    mimeType=file.content_type,
                    sizeBytes=len(file_bytes),
                    parser=parsed.parser,
                    notes=list(parsed.notes),
                    contentText=parsed.text,
                    ocrText=parsed.ocr_text,
                    tags=list(parsed.tags),
                    segments=list(parsed.segments),
                    structuredData=self._build_structured_data(
                        parsed_structured_data=parsed.structured_data,
                        document_type=parsed.document_type,
                        parser=parsed.parser,
                        file_bytes=file_bytes,
                        filename=filename,
                    ),
                )
            )
            warnings.extend(f"{filename}: {note}" for note in parsed.notes)
            await file.close()

        merged_documents = (
            workflow_session_store.merge_uploaded_documents(session_id, documents)
            if session_id
            else [document.model_copy(deep=True) for document in documents]
        )

        return WorkflowUploadResponse(
            sessionId=session_id or None,
            total=len(documents),
            documents=documents,
            mergedDocuments=merged_documents,
            warnings=warnings,
        )

    def _build_structured_data(
        self,
        *,
        parsed_structured_data: dict[str, object],
        document_type: str,
        parser: str,
        file_bytes: bytes,
        filename: str,
    ) -> dict[str, object]:
        """补充解析后的结构化数据。

        对 Excel 文档额外保存原始工作簿 token，供后续回填时保留模板结构。
        """
        structured_data = dict(parsed_structured_data)
        if document_type == "excel" and parser == "excel_parser" and file_bytes:
            structured_data["workbookUploadToken"] = workflow_upload_store.put_bytes(
                file_bytes,
                filename=filename,
            )
        return structured_data


workflow_upload_service = WorkflowUploadService()
