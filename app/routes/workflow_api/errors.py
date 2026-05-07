"""工作流路由错误转换。"""

from fastapi import HTTPException

from app.services.workflow.errors import WorkflowServiceError


def workflow_http_exception(exc: WorkflowServiceError) -> HTTPException:
    """把服务层异常转换成 FastAPI HTTPException。"""
    return HTTPException(status_code=exc.status_code, detail=str(exc))
