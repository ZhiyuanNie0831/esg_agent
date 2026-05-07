"""执行服务。

按计划逐步调用技能，记录执行日志，并在失败时标记后续步骤为阻塞。
"""

import logging
from datetime import datetime, timezone
from typing import Any

from app.schemas.workflow import (
    ExecutionLogEntry,
    IntentionAnalysis,
    PlanStep,
    PreparedDocument,
    WorkflowLogKind,
)
from app.services.workflow.skills.base import SkillExecutionContext
from app.services.workflow.skills.registry import WorkflowSkillRegistry

logger = logging.getLogger(__name__)


class WorkflowExecutionService:
    """逐步执行计划中的步骤并收集日志。"""

    def execute(
        self,
        task: str,
        intention: IntentionAnalysis,
        documents: list[PreparedDocument],
        plan: list[PlanStep],
        skill_registry: WorkflowSkillRegistry,
        agent_runtime: Any | None = None,
        local_fallback_enabled: bool = True,
        initial_skill_results: dict[str, dict[str, Any]] | None = None,
        initial_logs: list[ExecutionLogEntry] | None = None,
        start_from_step_id: str | None = None,
        reuse_source_job_id: str | None = None,
        stop_before_approval: bool = False,
    ) -> tuple[list[PlanStep], list[ExecutionLogEntry], dict[str, dict[str, Any]]]:
        """执行完整计划，返回执行后的步骤、日志和技能结果。"""
        executed_plan: list[PlanStep] = []
        execution_logs: list[ExecutionLogEntry] = []
        skill_results: dict[str, dict[str, Any]] = dict(initial_skill_results or {})
        initial_logs_by_step_id = {
            log.stepId: log.model_copy(deep=True)
            for log in initial_logs or []
            if log.stepId
        }
        blocked_from_step_number: int | None = None
        rerun_started = start_from_step_id is None

        logger.info(
            "workflow execution started: task=%s documents=%s plan_steps=%s intent=%s detected_intents=%s",
            task,
            len(documents),
            len(plan),
            intention.intentType,
            ",".join(intention.detectedIntentTypes),
        )

        for step in plan:
            if blocked_from_step_number is not None:
                break
            if stop_before_approval and step.checkpoint == "approval":
                break

            if not rerun_started and step.stepId != start_from_step_id:
                preserved_log = initial_logs_by_step_id.get(step.stepId)
                if preserved_log is not None:
                    executed_plan.append(step.model_copy(deep=True))
                    execution_logs.append(preserved_log)
                    continue
                reused_step, reused_log = self._reuse_step(
                    step=step,
                    documents=documents,
                    previous_results=skill_results,
                    reuse_source_job_id=reuse_source_job_id,
                )
                executed_plan.append(reused_step)
                execution_logs.append(reused_log)
                self._log_step_event(reused_log)
                continue
            rerun_started = True

            if step.status == "skipped":
                skipped_step, skipped_log = self._skip_step(
                    step=step,
                    documents=documents,
                    previous_results=skill_results,
                )
                executed_plan.append(skipped_step)
                execution_logs.append(skipped_log)
                self._log_step_event(skipped_log)
                continue

            previous_results = dict(skill_results)
            executed_step, log_entry, result = self._execute_step(
                step=step,
                task=task,
                intention=intention,
                documents=documents,
                previous_results=previous_results,
                skill_registry=skill_registry,
                agent_runtime=agent_runtime,
                local_fallback_enabled=local_fallback_enabled,
            )
            execution_logs.append(log_entry)
            self._log_step_event(log_entry)
            executed_plan.append(executed_step)

            if step.skill and result is not None and log_entry.status == "completed":
                skill_results[step.skill] = result

            if log_entry.status == "failed":
                blocked_from_step_number = step.stepNumber + 1
                break

        self._append_blocked_steps(
            plan=plan,
            documents=documents,
            executed_plan=executed_plan,
            execution_logs=execution_logs,
            skill_results=skill_results,
            blocked_from_step_number=blocked_from_step_number,
        )

        logger.info(
            "workflow execution finished: completed_steps=%s failed_logs=%s blocked_logs=%s skill_results=%s",
            len([step for step in executed_plan if step.status == "completed"]),
            len([log for log in execution_logs if log.status == "failed"]),
            len([log for log in execution_logs if log.status == "blocked"]),
            ",".join(sorted(skill_results)),
        )

        return executed_plan, execution_logs, skill_results

    def _reuse_step(
        self,
        *,
        step: PlanStep,
        documents: list[PreparedDocument],
        previous_results: dict[str, dict[str, Any]],
        reuse_source_job_id: str | None,
    ) -> tuple[PlanStep, ExecutionLogEntry]:
        """在局部重跑时复用起始步骤之前的执行结果。"""
        reused_at = datetime.now(timezone.utc)
        message = "已复用上游步骤结果，本次重跑跳过执行。"
        output_summary = {"reusedFromJobId": reuse_source_job_id}
        if step.skill and step.skill in previous_results:
            output_summary["resultKeys"] = sorted(previous_results[step.skill])
        return (
            step.model_copy(update={"status": "completed"}),
            self._build_log_entry(
                step=step,
                status="completed",
                message=message,
                started_at=reused_at,
                finished_at=reused_at,
                kind=self._resolve_log_kind(step),
                executor="workflow_system",
                input_summary=self._build_input_summary(
                    step=step,
                    documents=documents,
                    previous_results=previous_results,
                ),
                output_summary=output_summary,
            ),
        )

    def _skip_step(
        self,
        *,
        step: PlanStep,
        documents: list[PreparedDocument],
        previous_results: dict[str, dict[str, Any]],
    ) -> tuple[PlanStep, ExecutionLogEntry]:
        """记录一个被显式禁用的步骤。"""
        skipped_at = datetime.now(timezone.utc)
        return (
            step.model_copy(update={"status": "skipped"}),
            self._build_log_entry(
                step=step,
                status="skipped",
                message="该步骤已被计划覆写禁用，未执行。",
                started_at=skipped_at,
                finished_at=skipped_at,
                kind=self._resolve_log_kind(step),
                executor="workflow_system",
                input_summary=self._build_input_summary(
                    step=step,
                    documents=documents,
                    previous_results=previous_results,
                ),
                output_summary={"disabledByPlanOverride": True},
            ),
        )

    def _execute_step(
        self,
        *,
        step: PlanStep,
        task: str,
        intention: IntentionAnalysis,
        documents: list[PreparedDocument],
        previous_results: dict[str, dict[str, Any]],
        skill_registry: WorkflowSkillRegistry,
        agent_runtime: Any | None,
        local_fallback_enabled: bool,
    ) -> tuple[PlanStep, ExecutionLogEntry, dict[str, Any] | None]:
        """根据步骤类型分发到审批、系统步骤或技能步骤。"""
        if step.checkpoint == "approval":
            return self._complete_checkpoint_step(
                step=step,
                documents=documents,
                previous_results=previous_results,
            )
        if step.skill is None:
            return self._complete_system_step(
                step=step,
                documents=documents,
                previous_results=previous_results,
            )
        return self._execute_skill_step(
            step=step,
            task=task,
            intention=intention,
            documents=documents,
            previous_results=previous_results,
            skill_registry=skill_registry,
            agent_runtime=agent_runtime,
            local_fallback_enabled=local_fallback_enabled,
        )

    def _complete_checkpoint_step(
        self,
        *,
        step: PlanStep,
        documents: list[PreparedDocument],
        previous_results: dict[str, dict[str, Any]],
    ) -> tuple[PlanStep, ExecutionLogEntry, None]:
        """完成人工审批检查点。"""
        checkpoint_at = datetime.now(timezone.utc)
        log_entry = self._build_log_entry(
            step=step,
            status="completed",
            message="已通过人工确认，继续执行后续步骤。",
            started_at=checkpoint_at,
            finished_at=checkpoint_at,
            kind="checkpoint",
            executor="human_review",
            input_summary=self._build_input_summary(
                step=step,
                documents=documents,
                previous_results=previous_results,
            ),
            output_summary={
                "checkpointResult": "approved",
                "stepOutputs": list(step.outputs),
            },
        )
        return step.model_copy(update={"status": "completed"}), log_entry, None

    def _complete_system_step(
        self,
        *,
        step: PlanStep,
        documents: list[PreparedDocument],
        previous_results: dict[str, dict[str, Any]],
    ) -> tuple[PlanStep, ExecutionLogEntry, None]:
        """完成不调用技能的系统步骤。"""
        started_at = datetime.now(timezone.utc)
        finished_at = datetime.now(timezone.utc)
        log_entry = self._build_log_entry(
            step=step,
            status="completed",
            message=self._build_system_step_message(step),
            started_at=started_at,
            finished_at=finished_at,
            kind="system",
            executor="workflow_system",
            input_summary=self._build_input_summary(
                step=step,
                documents=documents,
                previous_results=previous_results,
            ),
            output_summary={
                "stepOutputs": list(step.outputs),
                "skillResultsAvailable": sorted(previous_results),
            },
        )
        return step.model_copy(update={"status": "completed"}), log_entry, None

    def _execute_skill_step(
        self,
        *,
        step: PlanStep,
        task: str,
        intention: IntentionAnalysis,
        documents: list[PreparedDocument],
        previous_results: dict[str, dict[str, Any]],
        skill_registry: WorkflowSkillRegistry,
        agent_runtime: Any | None,
        local_fallback_enabled: bool,
    ) -> tuple[PlanStep, ExecutionLogEntry, dict[str, Any] | None]:
        """执行一个具体技能，并记录成功或失败日志。"""
        skill = skill_registry.require(step.skill)
        self._log_skill_start(
            step=step,
            skill_title=skill.title,
            documents=documents,
            previous_results=previous_results,
        )
        started_at = datetime.now(timezone.utc)

        try:
            result = skill.execute(
                SkillExecutionContext(
                    task=task,
                    intention=intention,
                    documents=documents,
                    inputs=step.inputs,
                    previous_results=previous_results,
                    agent_runtime=agent_runtime,
                    local_fallback_enabled=local_fallback_enabled,
                )
            )
        except Exception as exc:  # pragma: no cover - safety net for pluggable skills
            finished_at = datetime.now(timezone.utc)
            log_entry = self._build_log_entry(
                step=step,
                status="failed",
                message=str(exc),
                started_at=started_at,
                finished_at=finished_at,
                kind="skill",
                executor="local_skill",
                input_summary=self._build_input_summary(
                    step=step,
                    documents=documents,
                    previous_results=previous_results,
                ),
                output_summary={"errorType": type(exc).__name__},
            )
            logger.exception(
                "workflow skill failed: step=%s title=%s skill=%s duration_ms=%s",
                step.stepNumber,
                step.title,
                step.skill,
                log_entry.durationMs,
            )
            return step.model_copy(update={"status": "failed"}), log_entry, None

        finished_at = datetime.now(timezone.utc)
        log_entry = self._build_log_entry(
            step=step,
            status="completed",
            message=f"技能“{skill.title}”执行成功。",
            started_at=started_at,
            finished_at=finished_at,
            kind="skill",
            executor=self._resolve_executor(result),
            input_summary=self._build_input_summary(
                step=step,
                documents=documents,
                previous_results=previous_results,
            ),
            output_summary=self._build_output_summary(result),
            outputPreview=self._build_output_preview(result),
        )
        return step.model_copy(update={"status": "completed"}), log_entry, result

    def _append_blocked_steps(
        self,
        *,
        plan: list[PlanStep],
        documents: list[PreparedDocument],
        executed_plan: list[PlanStep],
        execution_logs: list[ExecutionLogEntry],
        skill_results: dict[str, dict[str, Any]],
        blocked_from_step_number: int | None,
    ) -> None:
        """在前置失败后，把剩余步骤补成 blocked 状态。"""
        executed_step_numbers = {step.stepNumber for step in executed_plan}
        for step in plan:
            if step.stepNumber in executed_step_numbers:
                continue

            step_status = "blocked" if blocked_from_step_number is not None else step.status
            executed_plan.append(step.model_copy(update={"status": step_status}))
            if blocked_from_step_number is None:
                continue

            blocked_at = datetime.now(timezone.utc)
            log_entry = self._build_log_entry(
                step=step,
                status="blocked",
                message="前置步骤失败，当前步骤未执行。",
                started_at=blocked_at,
                finished_at=blocked_at,
                kind=self._resolve_log_kind(step),
                executor="workflow_system",
                input_summary=self._build_input_summary(
                    step=step,
                    documents=documents,
                    previous_results=skill_results,
                ),
                output_summary={"blockedByFailure": True},
            )
            execution_logs.append(log_entry)
            self._log_step_event(log_entry)

    def _build_output_preview(self, result: dict[str, Any]) -> str:
        """从技能结果里截取一段简短预览，用于日志展示。"""
        if "summary" in result:
            return str(result["summary"])[:180]
        if "revisedDocument" in result:
            return str(result["revisedDocument"])[:180]

        compact_pairs = ", ".join(f"{key}={value}" for key, value in result.items())
        return compact_pairs[:180]

    def _build_log_entry(
        self,
        *,
        step: PlanStep,
        status: str,
        message: str,
        started_at: datetime,
        finished_at: datetime,
        kind: WorkflowLogKind,
        executor: str,
        input_summary: dict[str, Any],
        output_summary: dict[str, Any],
        outputPreview: str | None = None,
    ) -> ExecutionLogEntry:
        """统一构造执行日志对象。"""
        duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        return ExecutionLogEntry(
            stepId=step.stepId,
            stepNumber=step.stepNumber,
            title=step.title,
            skill=step.skill,
            kind=kind,
            executor=executor,
            status=status,
            message=message,
            dependsOn=list(step.dependsOn),
            inputSummary=input_summary,
            outputSummary=output_summary,
            startedAt=started_at,
            finishedAt=finished_at,
            durationMs=duration_ms,
            outputPreview=outputPreview,
        )

    def _build_input_summary(
        self,
        *,
        step: PlanStep,
        documents: list[PreparedDocument],
        previous_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """整理步骤输入摘要，方便问题排查。"""
        return {
            "documentCount": len(documents),
            "documentNames": [document.name for document in documents[:4]],
            "segmentCount": sum(len(document.segments) for document in documents),
            "planInputs": dict(step.inputs),
            "requiresApproval": step.requiresApproval,
            "dependsOn": list(step.dependsOn),
            "availablePreviousResults": sorted(previous_results),
        }

    def _build_output_summary(self, result: dict[str, Any]) -> dict[str, Any]:
        """整理技能输出的概要信息。"""
        export_files = result.get("exportFiles")
        artifact_ids = [
            str(item.get("artifactId") or "").strip()
            for item in export_files
            if isinstance(export_files, list) and isinstance(item, dict)
            and str(item.get("artifactId") or "").strip()
        ] if isinstance(export_files, list) else []
        return {
            "resultKeys": sorted(result),
            "source": str(result.get("source", "local_skill")),
            "hasSummary": bool(result.get("summary")),
            "hasRevisedDocument": bool(result.get("revisedDocument")),
            "evidenceCount": len(result.get("evidenceRefs") or result.get("evidence") or []),
            "artifactIds": artifact_ids,
        }

    def _resolve_executor(self, result: dict[str, Any]) -> str:
        """把技能结果里的来源字段映射成执行器标识。"""
        source = str(result.get("source", "") or "").strip().lower()
        if source == "agent":
            return "model_api_agent"
        if source:
            return source
        return "local_skill"

    def _build_system_step_message(self, step: PlanStep) -> str:
        """为系统步骤生成默认日志文案。"""
        if step.title == "检查输入材料":
            return "已完成输入材料检查，并准备进入后续步骤。"
        if step.title == "整理最终输出":
            return "已整理所有执行结果，准备输出最终结论。"
        return "系统步骤已完成。"

    def _resolve_log_kind(self, step: PlanStep) -> WorkflowLogKind:
        """根据步骤类型推断日志种类。"""
        if step.checkpoint:
            return "checkpoint"
        if step.skill:
            return "skill"
        return "system"

    def _log_skill_start(
        self,
        *,
        step: PlanStep,
        skill_title: str,
        documents: list[PreparedDocument],
        previous_results: dict[str, dict[str, Any]],
    ) -> None:
        """输出技能开始执行的日志。"""
        logger.info(
            "workflow skill started: step=%s title=%s skill=%s documents=%s depends_on=%s previous_results=%s",
            step.stepNumber,
            skill_title,
            step.skill,
            len(documents),
            ",".join(str(item) for item in step.dependsOn) or "-",
            ",".join(sorted(previous_results)) or "-",
        )

    def _log_step_event(self, log_entry: ExecutionLogEntry) -> None:
        """输出单步执行完成后的日志。"""
        logger.info(
            "workflow step %s: step=%s title=%s kind=%s executor=%s duration_ms=%s depends_on=%s",
            log_entry.status,
            log_entry.stepNumber,
            log_entry.title,
            log_entry.kind,
            log_entry.executor or "-",
            log_entry.durationMs if log_entry.durationMs is not None else "-",
            ",".join(str(item) for item in log_entry.dependsOn) or "-",
        )
