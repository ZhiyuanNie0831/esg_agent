"""后台作业恢复上下文。

把审批恢复、局部重跑和已保存结果复用的细节从总服务中拆出来。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schemas.workflow import (
    ExecutionLogEntry,
    WorkflowJobSnapshot,
    WorkflowJobStatus,
    WorkflowPlanResponse,
)
from app.services.workflow.errors import WorkflowConfigurationError
from app.services.workflow.skills.registry import WorkflowSkillRegistry


@dataclass(slots=True)
class WorkflowJobResumeContext:
    """一次后台作业执行前可复用的上下文。"""

    initial_skill_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    initial_logs: list[ExecutionLogEntry] | None = None
    start_from_step_id: str | None = None
    reuse_source_job_id: str | None = None
    saved_plan_response: WorkflowPlanResponse | None = None


class WorkflowJobResumeService:
    """负责决定后台 job 应从哪里继续执行。"""

    def __init__(self, skill_registry: WorkflowSkillRegistry) -> None:
        self._skill_registry = skill_registry

    def build_context(
        self,
        snapshot: WorkflowJobSnapshot,
        *,
        source_snapshot: WorkflowJobSnapshot | None = None,
    ) -> WorkflowJobResumeContext:
        """为当前 job 构造执行器需要的恢复参数。"""
        if snapshot.reuseSourceJobId:
            return self._build_rerun_context(snapshot, source_snapshot=source_snapshot)
        if snapshot.approved:
            return self._build_approval_context(snapshot)
        return WorkflowJobResumeContext()

    def validate_rerun_source(self, source_snapshot: WorkflowJobSnapshot, from_step_id: str) -> None:
        """校验局部重跑是否具备足够的上游结果。"""
        if not any(step.stepId == from_step_id for step in source_snapshot.plan):
            raise WorkflowConfigurationError(f"未知 stepId，无法重跑：{from_step_id}")

        reusable_results = self.extract_skill_results(source_snapshot)
        for step in source_snapshot.plan:
            if step.stepId == from_step_id:
                break
            if step.skill and step.status == "completed" and step.skill not in reusable_results:
                raise WorkflowConfigurationError(f"步骤 {step.title} 没有可复用的结果，无法从中间步骤重跑。")

    def extract_skill_results(self, snapshot: WorkflowJobSnapshot) -> dict[str, dict[str, Any]]:
        """从 finalOutput artifacts 中取回已完成技能的结构化结果。"""
        if snapshot.finalOutput is None:
            return {}
        artifacts = snapshot.finalOutput.artifacts or {}
        skill_results = artifacts.get("技能结果", {})
        return dict(skill_results) if isinstance(skill_results, dict) else {}

    def map_execute_status(self, status: str) -> WorkflowJobStatus:
        """把同步执行状态映射到后台 job 状态。"""
        if status == "awaiting_confirmation":
            return "awaiting_confirmation"
        if status == "completed":
            return "completed"
        return "blocked"

    def _build_rerun_context(
        self,
        snapshot: WorkflowJobSnapshot,
        *,
        source_snapshot: WorkflowJobSnapshot | None,
    ) -> WorkflowJobResumeContext:
        if source_snapshot is None:
            return WorkflowJobResumeContext(reuse_source_job_id=snapshot.reuseSourceJobId)

        start_from_step_id = str(
            source_snapshot.request.context.metadata.get("_rerunFromStepId")
            or snapshot.request.context.metadata.get("_rerunFromStepId")
            or ""
        ).strip() or None
        return WorkflowJobResumeContext(
            initial_skill_results=self.extract_skill_results(source_snapshot),
            start_from_step_id=start_from_step_id,
            reuse_source_job_id=snapshot.reuseSourceJobId,
        )

    def _build_approval_context(self, snapshot: WorkflowJobSnapshot) -> WorkflowJobResumeContext:
        saved_plan_response = self._build_saved_plan_response(snapshot)
        if saved_plan_response is None:
            return WorkflowJobResumeContext()

        return WorkflowJobResumeContext(
            initial_skill_results=self.extract_skill_results(snapshot),
            initial_logs=snapshot.logs,
            start_from_step_id=self._resolve_resume_start_step_id(snapshot),
            saved_plan_response=saved_plan_response,
        )

    def _build_saved_plan_response(self, snapshot: WorkflowJobSnapshot) -> WorkflowPlanResponse | None:
        """把待审批作业中已保存的规划快照恢复成可继续执行的计划响应。"""
        if not snapshot.plan or snapshot.intention is None or snapshot.missingDocuments is None:
            return None

        status = "needs_documents" if snapshot.missingDocuments.missingKinds else "ready_to_execute"
        suggested_skills = []
        seen_skill_names: set[str] = set()
        for step in snapshot.plan:
            if not step.skill or step.skill in seen_skill_names:
                continue
            skill = self._skill_registry.get(step.skill)
            if skill is None:
                continue
            suggested_skills.append(skill.descriptor())
            seen_skill_names.add(step.skill)

        return WorkflowPlanResponse(
            requestId=snapshot.requestId,
            sessionId=snapshot.sessionId,
            status=status,
            intention=snapshot.intention,
            preparedDocuments=snapshot.preparedDocuments,
            missingDocuments=snapshot.missingDocuments,
            suggestedSkills=suggested_skills,
            plan=[step.model_copy(deep=True) for step in snapshot.plan],
            summary="使用已保存的待审批计划继续执行。",
        )

    def _resolve_resume_start_step_id(self, snapshot: WorkflowJobSnapshot) -> str | None:
        """审批恢复时从待确认点继续；缺少确认点时从第一个未完成步骤继续。"""
        for step in snapshot.plan:
            if step.checkpoint == "approval" and step.status != "completed":
                return step.stepId
        for step in snapshot.plan:
            if step.status not in {"completed", "skipped"}:
                return step.stepId
        return None
