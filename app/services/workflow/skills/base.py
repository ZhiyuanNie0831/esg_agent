"""技能体系的基础抽象。

定义技能运行时上下文，以及所有技能需要实现的公共接口。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.schemas.workflow import IntentionAnalysis, PreparedDocument, SkillDescriptor
from app.services.workflow.errors import require_local_fallback
from app.services.workflow.segments import select_documents_for_task, serialize_documents_for_task


@dataclass(slots=True)
class SkillExecutionContext:
    """单个技能执行时可访问的上下文。"""

    task: str
    intention: IntentionAnalysis
    documents: list[PreparedDocument]
    inputs: dict[str, Any] = field(default_factory=dict)
    previous_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent_runtime: Any | None = None
    local_fallback_enabled: bool = True

    def resolve_documents(
        self,
        *,
        max_documents: int | None = None,
        allowed_types: set[str] | None = None,
    ) -> list[PreparedDocument]:
        """返回与当前任务更相关的文档；命中失败时回退到原始输入。"""
        documents = select_documents_for_task(
            self.task,
            self.documents,
            max_documents=max_documents,
            allowed_types=allowed_types,
        )
        return documents or self.documents

    def require_local_fallback(self, capability: str) -> None:
        """在禁用本地回退时，明确要求当前能力必须由 agent 提供。"""
        require_local_fallback(
            local_fallback_enabled=self.local_fallback_enabled,
            agent_active=self.agent_runtime is not None,
            capability=capability,
        )

    def build_document_context(
        self,
        *,
        max_documents: int,
        max_segments_per_document: int,
        max_total_segments: int,
        segment_text_limit: int,
        allowed_types: set[str] | None = None,
    ) -> tuple[list[PreparedDocument], dict[str, Any]]:
        """返回筛选后的文档，以及对应的任务上下文。"""
        documents = self.resolve_documents(
            max_documents=max_documents,
            allowed_types=allowed_types,
        )
        return documents, serialize_documents_for_task(
            self.task,
            documents,
            max_documents=max_documents,
            max_segments_per_document=max_segments_per_document,
            max_total_segments=max_total_segments,
            segment_text_limit=segment_text_limit,
        )


class WorkflowSkill(ABC):
    """全部可插拔工作流技能的基类。"""

    name: str
    title: str
    description: str
    input_hint: str = ""
    output_hint: str = ""
    requires_approval: bool = False
    tags: tuple[str, ...] = ()

    def descriptor(self) -> SkillDescriptor:
        """把技能实例转换成对外展示的描述信息。"""
        return SkillDescriptor(
            name=self.name,
            title=self.title,
            description=self.description,
            inputHint=self.input_hint,
            outputHint=self.output_hint,
            requiresApproval=self.requires_approval,
            tags=list(self.tags),
        )

    @abstractmethod
    def execute(self, context: SkillExecutionContext) -> dict[str, Any]:
        """执行技能，并返回可序列化结果。"""
