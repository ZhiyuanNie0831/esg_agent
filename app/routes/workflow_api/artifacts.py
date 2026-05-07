"""工作流产物下载 API。"""

from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services.workflow.file_store import workflow_file_store

router = APIRouter()


@router.get("/artifacts/{artifact_id}")
async def download_artifact(artifact_id: str) -> Response:
    """下载一个持久化产物。"""
    record, data = workflow_file_store.read_artifact(artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    if data is None:
        raise HTTPException(status_code=410, detail="Artifact content missing.")
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(record.filename)}",
    }
    return Response(content=data, media_type=record.mime_type, headers=headers)
