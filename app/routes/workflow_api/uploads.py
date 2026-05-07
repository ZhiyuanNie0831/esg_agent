"""工作流材料上传 API。"""

from fastapi import APIRouter, File, Form, UploadFile

from app.schemas.workflow import WorkflowUploadResponse
from app.services.workflow.uploads import workflow_upload_service

router = APIRouter()


@router.post("/uploads", response_model=WorkflowUploadResponse)
async def upload_documents(
    files: list[UploadFile] = File(...),
    session_id: str | None = Form(None, alias="sessionId"),
) -> WorkflowUploadResponse:
    """读取上传文件，并转换成统一的工作流文档结构。"""
    return await workflow_upload_service.upload(files, session_id=session_id)
