"""应用入口。

负责创建 FastAPI 实例、挂载静态资源，并暴露工作流相关的健康检查与前端页面入口。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes.workflow import router as workflow_router
from app.services.workflow.persistence import workflow_database

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
WORKFLOW_BUNDLE_PATH = STATIC_DIR / "workflow_bundle.txt"

app = FastAPI(
    title="agent_v0",
    version="0.1.0",
    description="Workflow agent surface for intent understanding, skill planning, manual confirmation, and execution.",
)


@app.get("/health")
async def health() -> dict[str, object]:
    """返回前端需要的服务运行状态。"""
    api_configured = bool(settings.model_api_key)
    return {
        "ok": True,
        "service": "agent_v0",
        "provider": settings.model_api_provider,
        "providerLabel": settings.model_api_provider_label,
        "protocol": settings.model_api_protocol,
        "apiConfigured": api_configured,
        "apiBaseUrl": settings.model_api_base_url,
        "model": settings.model_api_model,
        "workflowMode": "agent_orchestrated_with_local_skills",
        "agentEnabled": api_configured and settings.model_api_agent_enabled,
        "ocrEnabled": bool(settings.model_api_ocr_key) and settings.model_api_ocr_enabled,
        "ocrProvider": settings.model_api_ocr_provider,
        "ocrProviderLabel": settings.model_api_ocr_provider_label,
        "ocrProtocol": settings.model_api_ocr_protocol,
        "ocrApiConfigured": bool(settings.model_api_ocr_key),
        "ocrApiBaseUrl": settings.model_api_ocr_base_url,
        "ocrModel": settings.model_api_ocr_model,
        "ocrPdfMode": settings.model_api_ocr_pdf_mode,
        "reviewEnabled": bool(settings.model_api_review_key) and settings.model_api_review_enabled,
        "reviewProvider": settings.model_api_review_provider,
        "reviewProviderLabel": settings.model_api_review_provider_label,
        "reviewProtocol": settings.model_api_review_protocol,
        "reviewApiConfigured": bool(settings.model_api_review_key),
        "reviewApiBaseUrl": settings.model_api_review_base_url,
        "reviewModel": settings.model_api_review_model,
        "reviewBlockOnHighRisk": settings.model_api_review_block_on_high_risk,
        "confirmationMode": "risk_based",
        "databaseBackend": workflow_database.engine.dialect.name,
        "workerCount": settings.workflow_worker_count,
    }


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """返回单页演示前端。"""
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/workflow-bundle", include_in_schema=False)
async def workflow_bundle() -> FileResponse:
    """返回前端脚本资源。

    这里使用 `.txt` 文件承载脚本内容，避免源码导出时额外携带独立的 `.js` 文件。
    """
    return FileResponse(
        WORKFLOW_BUNDLE_PATH,
        media_type="text/javascript",
        headers={"Cache-Control": "no-store"},
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(workflow_router, prefix="/api/workflow", tags=["workflow"])
