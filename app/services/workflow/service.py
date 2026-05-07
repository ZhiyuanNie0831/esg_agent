"""工作流总服务。

负责串联输入标准化、意图分析、缺失材料检查、规划、执行、后台作业和最终总结。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from app.config import settings
from app.schemas.workflow import (
    ApproveWorkflowJobRequest,
    CreateWorkflowJobRequest,
    ExecutionLogEntry,
    PlanOverrides,
    SkillCatalogResponse,
    WorkflowExecuteRequest,
    WorkflowExecuteResponse,
    WorkflowJobSnapshot,
    WorkflowPlanResponse,
    WorkflowRunRequest,
)
from app.services.workflow.agent_runtime import WorkflowModelAgentRuntime
from app.services.workflow.document_check import WorkflowDocumentCheckService
from app.services.workflow.errors import (
    WorkflowAgentUnavailableError,
    WorkflowConfigurationError,
    WorkflowServiceError,
)
from app.services.workflow.execution import WorkflowExecutionService
from app.services.workflow.input import WorkflowInputService
from app.services.workflow.intention import WorkflowIntentionService
from app.services.workflow.job_resume import WorkflowJobResumeService
from app.services.workflow.job_store import workflow_job_store
from app.services.workflow.plan_overrides import apply_plan_overrides, merge_plan_overrides
from app.services.workflow.planning import WorkflowPlanningService
from app.services.workflow.session_store import workflow_session_store
from app.services.workflow.skills import build_default_skill_registry
from app.services.workflow.summary import WorkflowSummaryService


class WorkflowAgentService:
    """工作流引擎的总编排入口。"""

    def __init__(self):
        self._lock = RLock()
        self._agent_runtime = WorkflowModelAgentRuntime()
        self._input_service = WorkflowInputService()
        self._document_check_service = WorkflowDocumentCheckService()
        self._planning_service = WorkflowPlanningService()
        self._execution_service = WorkflowExecutionService()
        self._skill_registry = build_default_skill_registry()
        self._job_resume_service = WorkflowJobResumeService(self._skill_registry)
        self._job_store = workflow_job_store
        self._job_executor = ThreadPoolExecutor(max_workers=settings.workflow_worker_count)
        self._resume_pending_jobs()

    def list_skills(self) -> SkillCatalogResponse:
        """返回系统当前可用的技能清单。"""
        skills = self._skill_registry.list_descriptors()
        return SkillCatalogResponse(total=len(skills), skills=skills)

    def plan(self, request: WorkflowRunRequest) -> WorkflowPlanResponse:
        """只执行规划阶段，不真正运行技能。"""
        _, plan_response = self._plan_request(request)
        return plan_response

    def execute(self, request: WorkflowExecuteRequest) -> WorkflowExecuteResponse:
        """执行完整工作流，并返回日志和最终结果。"""
        response, _, _ = self._execute_request(
            request=request,
            plan_overrides=None,
            inline_download_content=True,
        )
        return response

    def create_job(self, request: CreateWorkflowJobRequest) -> WorkflowJobSnapshot:
        """创建一个后台工作流作业。"""
        execute_request = WorkflowExecuteRequest.model_validate(
            request.model_dump(exclude={"planOverrides"}, mode="json")
        )
        snapshot = WorkflowJobSnapshot(
            requestId=uuid4(),
            sessionId=request.sessionId,
            status="queued",
            task=request.task,
            approved=request.approved,
            request=execute_request,
            planOverrides=request.planOverrides,
        )
        snapshot = self._job_store.create(snapshot)
        if snapshot.sessionId:
            workflow_session_store.set_latest_job_id(snapshot.sessionId, snapshot.jobId)
        self._submit_job(snapshot.jobId)
        return snapshot

    def get_job(self, job_id: str) -> WorkflowJobSnapshot | None:
        """读取一个后台作业。"""
        return self._job_store.get(job_id)

    def approve_job(self, job_id: str, request: ApproveWorkflowJobRequest) -> WorkflowJobSnapshot:
        """审批后恢复一个已暂停的后台作业。"""
        snapshot = self._job_store.get(job_id)
        if snapshot is None:
            raise WorkflowConfigurationError("Job not found.")
        if snapshot.status != "awaiting_confirmation":
            raise WorkflowConfigurationError("当前作业不处于待审批状态。")

        snapshot.approved = bool(request.approved)
        snapshot.request = snapshot.request.model_copy(update={"approved": snapshot.approved})
        snapshot.planOverrides = merge_plan_overrides(snapshot.planOverrides, request.planOverrides)
        snapshot.status = "queued"
        snapshot.error = None
        snapshot.updatedAt = self._now()
        snapshot.completedAt = None
        snapshot = self._job_store.save(snapshot)
        self._submit_job(snapshot.jobId)
        return snapshot

    def rerun_job(self, job_id: str, from_step_id: str) -> WorkflowJobSnapshot:
        """从指定步骤克隆并重跑一个作业。"""
        source_snapshot = self._job_store.get(job_id)
        if source_snapshot is None:
            raise WorkflowConfigurationError("Job not found.")
        self._job_resume_service.validate_rerun_source(source_snapshot, from_step_id)

        metadata = dict(source_snapshot.request.context.metadata)
        metadata["_rerunFromStepId"] = from_step_id
        cloned_request = source_snapshot.request.model_copy(
            update={
                "context": source_snapshot.request.context.model_copy(
                    update={"metadata": metadata}
                )
            }
        )
        snapshot = WorkflowJobSnapshot(
            requestId=uuid4(),
            sessionId=source_snapshot.sessionId,
            status="queued",
            task=source_snapshot.task,
            approved=cloned_request.approved,
            request=cloned_request,
            planOverrides=source_snapshot.planOverrides.model_copy(deep=True),
            reuseSourceJobId=source_snapshot.jobId,
        )
        snapshot = self._job_store.create(snapshot)
        if snapshot.sessionId:
            workflow_session_store.set_latest_job_id(snapshot.sessionId, snapshot.jobId)
        self._submit_job(snapshot.jobId)
        return snapshot

    def _execute_request(
        self,
        *,
        request: WorkflowExecuteRequest,
        plan_overrides: PlanOverrides | None,
        inline_download_content: bool,
        job_id: str | None = None,
        initial_skill_results: dict[str, dict[str, Any]] | None = None,
        initial_logs: list[ExecutionLogEntry] | None = None,
        start_from_step_id: str | None = None,
        reuse_source_job_id: str | None = None,
        saved_plan_response: WorkflowPlanResponse | None = None,
    ) -> tuple[WorkflowExecuteResponse, WorkflowPlanResponse, dict[str, dict[str, Any]]]:
        """执行同步或后台工作流请求。"""
        if saved_plan_response is None:
            active_agent_runtime, plan_response = self._plan_request(request)
        else:
            active_agent_runtime = self._resolve_agent_runtime(request.agentMode)
            self._validate_runtime_configuration(
                agent_mode=request.agentMode,
                local_fallback_enabled=request.localFallbackEnabled,
                agent_runtime=active_agent_runtime,
            )
            plan_response = saved_plan_response
        effective_plan = apply_plan_overrides(plan_response.plan, plan_overrides)
        summary_service = WorkflowSummaryService(
            agent_runtime=active_agent_runtime,
            local_fallback_enabled=request.localFallbackEnabled,
            job_id=job_id,
            inline_download_content=inline_download_content,
        )

        if plan_response.status == "needs_documents":
            response = self._build_needs_documents_response(
                request=request,
                plan_response=plan_response,
                effective_plan=effective_plan,
                summary_service=summary_service,
            )
            return response, plan_response, {}

        if self._requires_confirmation(effective_plan, approved=request.approved):
            preview_plan, preview_logs, preview_skill_results = self._execution_service.execute(
                task=request.task,
                intention=plan_response.intention,
                documents=plan_response.preparedDocuments,
                plan=effective_plan,
                skill_registry=self._skill_registry,
                agent_runtime=active_agent_runtime,
                local_fallback_enabled=request.localFallbackEnabled,
                initial_skill_results=initial_skill_results,
                initial_logs=initial_logs,
                start_from_step_id=start_from_step_id,
                reuse_source_job_id=reuse_source_job_id,
                stop_before_approval=True,
            )
            preview_output = None
            if preview_logs or preview_skill_results:
                preview_output = summary_service.build_output(
                    task=request.task,
                    intention=plan_response.intention,
                    documents=plan_response.preparedDocuments,
                    missing_documents=plan_response.missingDocuments,
                    logs=preview_logs,
                    skill_results=preview_skill_results,
                )
            response = WorkflowExecuteResponse(
                requestId=uuid4(),
                sessionId=request.sessionId,
                status="awaiting_confirmation",
                intention=plan_response.intention,
                preparedDocuments=plan_response.preparedDocuments,
                missingDocuments=plan_response.missingDocuments,
                plan=preview_plan,
                logs=preview_logs,
                executedSkills=list(preview_skill_results),
                finalOutput=preview_output,
            )
            self._save_session_execution_response(
                request=request,
                plan_response=plan_response,
                response=response,
            )
            return response, plan_response, preview_skill_results

        executed_plan, logs, skill_results = self._execution_service.execute(
            task=request.task,
            intention=plan_response.intention,
            documents=plan_response.preparedDocuments,
            plan=effective_plan,
            skill_registry=self._skill_registry,
            agent_runtime=active_agent_runtime,
            local_fallback_enabled=request.localFallbackEnabled,
            initial_skill_results=initial_skill_results,
            initial_logs=initial_logs,
            start_from_step_id=start_from_step_id,
            reuse_source_job_id=reuse_source_job_id,
        )
        execution_status = "blocked" if any(log.status == "failed" for log in logs) else "completed"
        final_output = summary_service.build_output(
            task=request.task,
            intention=plan_response.intention,
            documents=plan_response.preparedDocuments,
            missing_documents=plan_response.missingDocuments,
            logs=logs,
            skill_results=skill_results,
        )

        response = WorkflowExecuteResponse(
            requestId=uuid4(),
            sessionId=request.sessionId,
            status=execution_status,
            intention=plan_response.intention,
            preparedDocuments=plan_response.preparedDocuments,
            missingDocuments=plan_response.missingDocuments,
            plan=executed_plan,
            logs=logs,
            executedSkills=list(skill_results),
            finalOutput=final_output,
        )
        self._save_session_execution_response(
            request=request,
            plan_response=plan_response,
            response=response,
        )
        return response, plan_response, skill_results

    def _plan_request(
        self,
        request: WorkflowRunRequest,
    ) -> tuple[Any | None, WorkflowPlanResponse]:
        """统一执行规划前半段逻辑，供 `plan` 和 `execute` 复用。"""
        active_agent_runtime = self._resolve_agent_runtime(request.agentMode)
        self._validate_runtime_configuration(
            agent_mode=request.agentMode,
            local_fallback_enabled=request.localFallbackEnabled,
            agent_runtime=active_agent_runtime,
        )
        intention_service = WorkflowIntentionService(
            agent_runtime=active_agent_runtime,
            local_fallback_enabled=request.localFallbackEnabled,
        )
        prepared_documents = self._input_service.prepare_documents(request.documents)
        intention = intention_service.analyze(
            task=request.task,
            documents=prepared_documents,
            preferred_skills=request.preferredSkills,
            available_skills=self._skill_registry.list_descriptors(),
            agent_mode=request.agentMode,
        )
        missing_documents = self._document_check_service.check(
            required_kinds=intention.requiredDocumentKinds,
            documents=prepared_documents,
            document_required=intention.documentRequired,
        )
        status, suggested_skills, plan, summary = self._planning_service.build_plan(
            task=request.task,
            documents=prepared_documents,
            intention=intention,
            missing_documents=missing_documents,
            skill_registry=self._skill_registry,
            manual_confirm=request.manualConfirm,
        )
        plan_response = WorkflowPlanResponse(
            requestId=uuid4(),
            sessionId=request.sessionId,
            status=status,
            intention=intention,
            preparedDocuments=prepared_documents,
            missingDocuments=missing_documents,
            suggestedSkills=suggested_skills,
            plan=plan,
            summary=summary,
        )
        if request.sessionId:
            workflow_session_store.save_plan_response(
                session_id=request.sessionId,
                request=request,
                response=plan_response,
            )
        return active_agent_runtime, plan_response

    def _validate_runtime_configuration(
        self,
        *,
        agent_mode: str,
        local_fallback_enabled: bool,
        agent_runtime: Any | None,
    ) -> None:
        """校验请求级执行模式，避免两边都关或仅启用不可用 agent。"""
        if agent_mode == "off" and not local_fallback_enabled:
            raise WorkflowConfigurationError("模型 API agent 和本地回退至少开启一种。")

        if agent_mode != "off" and agent_runtime is None and not local_fallback_enabled:
            raise WorkflowAgentUnavailableError(
                "当前未启用模型 API agent，且已关闭本地回退，无法处理本次请求。"
            )

    def _build_needs_documents_response(
        self,
        *,
        request: WorkflowExecuteRequest,
        plan_response: WorkflowPlanResponse,
        effective_plan,
        summary_service: WorkflowSummaryService,
    ) -> WorkflowExecuteResponse:
        """构造“缺少材料，暂不能执行”的响应。"""
        final_output = summary_service.build_output(
            task=request.task,
            intention=plan_response.intention,
            documents=plan_response.preparedDocuments,
            missing_documents=plan_response.missingDocuments,
            logs=[],
            skill_results={},
        )
        response = WorkflowExecuteResponse(
            requestId=uuid4(),
            sessionId=request.sessionId,
            status="needs_documents",
            intention=plan_response.intention,
            preparedDocuments=plan_response.preparedDocuments,
            missingDocuments=plan_response.missingDocuments,
            plan=effective_plan,
            finalOutput=final_output,
        )
        self._save_session_execution_response(
            request=request,
            plan_response=plan_response,
            response=response,
        )
        return response

    def _requires_confirmation(self, plan, *, approved: bool) -> bool:
        """判断当前计划是否仍需人工确认。"""
        requires_confirmation = any(
            (step.checkpoint == "approval" or step.requiresApproval) and step.status != "skipped"
            for step in plan
        )
        return requires_confirmation and not approved

    def _resolve_agent_runtime(self, agent_mode: str):
        """根据请求级 agent 模式决定是否启用 agent 运行时。"""
        if agent_mode != "off" and self._agent_runtime.enabled:
            return self._agent_runtime
        return None

    def _save_session_execution_response(
        self,
        *,
        request: WorkflowRunRequest,
        plan_response: WorkflowPlanResponse,
        response: WorkflowExecuteResponse,
    ) -> None:
        if not request.sessionId:
            return

        workflow_session_store.save_execution_response(
            session_id=request.sessionId,
            request=request,
            plan_response=plan_response,
            response=response,
        )

    def _submit_job(self, job_id: str) -> None:
        self._job_executor.submit(self._run_job, job_id)

    def _run_job(self, job_id: str) -> None:
        snapshot = self._job_store.get(job_id)
        if snapshot is None:
            return

        with self._lock:
            snapshot.status = "running"
            snapshot.updatedAt = self._now()
            snapshot.error = None
        self._job_store.save(snapshot)

        try:
            source_snapshot = (
                self._job_store.get(snapshot.reuseSourceJobId)
                if snapshot.reuseSourceJobId
                else None
            )
            resume_context = self._job_resume_service.build_context(
                snapshot,
                source_snapshot=source_snapshot,
            )

            response, _, _ = self._execute_request(
                request=snapshot.request.model_copy(update={"approved": snapshot.approved}),
                plan_overrides=snapshot.planOverrides,
                inline_download_content=False,
                job_id=snapshot.jobId,
                initial_skill_results=resume_context.initial_skill_results,
                initial_logs=resume_context.initial_logs,
                start_from_step_id=resume_context.start_from_step_id,
                reuse_source_job_id=resume_context.reuse_source_job_id,
                saved_plan_response=resume_context.saved_plan_response,
            )
            snapshot.status = self._job_resume_service.map_execute_status(response.status)
            snapshot.plan = response.plan
            snapshot.intention = response.intention
            snapshot.preparedDocuments = response.preparedDocuments
            snapshot.missingDocuments = response.missingDocuments
            snapshot.logs = response.logs
            snapshot.executedSkills = response.executedSkills
            snapshot.finalOutput = response.finalOutput
            snapshot.updatedAt = self._now()
            snapshot.completedAt = None if snapshot.status == "awaiting_confirmation" else self._now()
            snapshot.error = None
            self._job_store.save(snapshot)
        except WorkflowServiceError as exc:
            snapshot.status = "failed"
            snapshot.updatedAt = self._now()
            snapshot.completedAt = self._now()
            snapshot.error = str(exc)
            self._job_store.save(snapshot)
        except Exception as exc:  # pragma: no cover - background safety net
            snapshot.status = "failed"
            snapshot.updatedAt = self._now()
            snapshot.completedAt = self._now()
            snapshot.error = f"{type(exc).__name__}: {exc}"
            self._job_store.save(snapshot)

    def _resume_pending_jobs(self) -> None:
        for job_id in self._job_store.list_resumable_job_ids():
            self._submit_job(job_id)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)


workflow_agent_service = WorkflowAgentService()
