"""工作流规划与同步执行 API。"""

from fastapi import APIRouter

from app.routes.workflow_api.errors import workflow_http_exception
from app.schemas.workflow import (
    WorkflowExecuteRequest,
    WorkflowExecuteResponse,
    WorkflowPlanResponse,
    WorkflowRunRequest,
)
from app.services.workflow import workflow_agent_service
from app.services.workflow.errors import WorkflowServiceError

router = APIRouter()


@router.post("/plan", response_model=WorkflowPlanResponse)
async def plan_workflow(request: WorkflowRunRequest) -> WorkflowPlanResponse:
    """分析意图、检查材料，并生成执行计划。"""
    try:
        return workflow_agent_service.plan(request)
    except WorkflowServiceError as exc:
        raise workflow_http_exception(exc) from exc


@router.post("/execute", response_model=WorkflowExecuteResponse)
async def execute_workflow(request: WorkflowExecuteRequest) -> WorkflowExecuteResponse:
    """执行已经确认过的工作流请求。"""
    try:
        return workflow_agent_service.execute(request)
    except WorkflowServiceError as exc:
        raise workflow_http_exception(exc) from exc
