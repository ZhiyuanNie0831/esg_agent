"""工作流 session API。"""

from fastapi import APIRouter, HTTPException

from app.schemas.workflow import (
    WorkflowSessionDeleteResponse,
    WorkflowSessionState,
)
from app.services.workflow.session_store import workflow_session_store

router = APIRouter()


@router.post("/sessions", response_model=WorkflowSessionState)
async def create_session() -> WorkflowSessionState:
    """创建一个新的工作流 session。"""
    return workflow_session_store.create_session()


@router.get("/sessions/{session_id}", response_model=WorkflowSessionState)
async def get_session(session_id: str) -> WorkflowSessionState:
    """读取一个已有 session 的状态快照。"""
    session = workflow_session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


@router.delete("/sessions/{session_id}", response_model=WorkflowSessionDeleteResponse)
async def delete_session(session_id: str) -> WorkflowSessionDeleteResponse:
    """删除一个 session。"""
    deleted = workflow_session_store.clear_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found.")
    return WorkflowSessionDeleteResponse(sessionId=session_id)
