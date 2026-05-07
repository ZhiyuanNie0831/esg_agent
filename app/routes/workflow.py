"""工作流 HTTP 路由聚合。

公开路径保持为 `/api/workflow/...`，具体入口按职责拆在 `app.routes.workflow_api`。
"""

from fastapi import APIRouter

from app.routes.workflow_api import artifacts, catalog, jobs, planning, sessions, uploads

router = APIRouter()

router.include_router(catalog.router)
router.include_router(uploads.router)
router.include_router(planning.router)
router.include_router(jobs.router)
router.include_router(artifacts.router)
router.include_router(sessions.router)
