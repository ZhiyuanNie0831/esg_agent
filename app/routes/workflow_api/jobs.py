"""后台工作流作业 API。"""

from fastapi import APIRouter, HTTPException

from app.routes.workflow_api.errors import workflow_http_exception
from app.schemas.workflow import (
    ApproveWorkflowJobRequest,
    CreateWorkflowJobRequest,
    RerunWorkflowJobRequest,
    WorkflowJobSnapshot,
)
from app.services.workflow import workflow_agent_service
from app.services.workflow.errors import WorkflowServiceError

router = APIRouter()


@router.post("/jobs", response_model=WorkflowJobSnapshot)
async def create_job(request: CreateWorkflowJobRequest) -> WorkflowJobSnapshot:
    """创建一个后台工作流作业。"""
    try:
        return workflow_agent_service.create_job(request)
    except WorkflowServiceError as exc:
        raise workflow_http_exception(exc) from exc


@router.get("/jobs/{job_id}", response_model=WorkflowJobSnapshot)
async def get_job(job_id: str) -> WorkflowJobSnapshot:
    """读取一个后台作业的状态。"""
    job = workflow_agent_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.post("/jobs/{job_id}/approve", response_model=WorkflowJobSnapshot)
async def approve_job(job_id: str, request: ApproveWorkflowJobRequest) -> WorkflowJobSnapshot:
    """审批后继续执行一个暂停作业。"""
    try:
        return workflow_agent_service.approve_job(job_id, request)
    except WorkflowServiceError as exc:
        raise workflow_http_exception(exc) from exc


@router.post("/jobs/{job_id}/rerun", response_model=WorkflowJobSnapshot)
async def rerun_job(job_id: str, request: RerunWorkflowJobRequest) -> WorkflowJobSnapshot:
    """从指定步骤重跑一个已有作业。"""
    try:
        return workflow_agent_service.rerun_job(job_id, request.fromStepId)
    except WorkflowServiceError as exc:
        raise workflow_http_exception(exc) from exc
