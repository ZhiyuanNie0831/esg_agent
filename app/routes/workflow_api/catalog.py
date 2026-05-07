"""工作流技能目录 API。"""

from fastapi import APIRouter

from app.schemas.workflow import SkillCatalogResponse
from app.services.workflow import workflow_agent_service

router = APIRouter()


@router.get("/skills", response_model=SkillCatalogResponse)
async def list_skills() -> SkillCatalogResponse:
    """返回当前注册的全部工作流技能。"""
    return workflow_agent_service.list_skills()
