"""技能注册表。

规划和执行阶段都通过这里查询技能，而不是直接依赖具体技能类。
"""

from app.schemas.workflow import SkillDescriptor
from app.services.workflow.skills.base import WorkflowSkill


class WorkflowSkillRegistry:
    """用于管理和查找技能实例的注册表。"""

    def __init__(self):
        self._skills: dict[str, WorkflowSkill] = {}

    def register(self, skill: WorkflowSkill) -> None:
        """注册一个技能实例。"""
        self._skills[skill.name] = skill

    def get(self, skill_name: str) -> WorkflowSkill | None:
        """按名称获取技能，不存在时返回空。"""
        return self._skills.get(skill_name)

    def list_names(self) -> list[str]:
        """返回当前全部技能名称。"""
        return list(self._skills)

    def require(self, skill_name: str) -> WorkflowSkill:
        """按名称获取技能，不存在时抛出异常。"""
        skill = self.get(skill_name)
        if skill is None:
            raise KeyError(f"Skill '{skill_name}' is not registered.")

        return skill

    def list_descriptors(self) -> list[SkillDescriptor]:
        """返回全部技能的展示描述。"""
        return [skill.descriptor() for skill in self._skills.values()]
