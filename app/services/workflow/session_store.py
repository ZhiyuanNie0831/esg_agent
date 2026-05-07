"""工作流 session 存储。

使用数据库持久化跨请求状态，同时保留与旧版 store 相同的公开接口。
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from app.schemas.workflow import (
    WorkflowDocument,
    WorkflowExecuteResponse,
    WorkflowPlanResponse,
    WorkflowRunRequest,
    WorkflowSessionState,
)
from app.services.workflow.persistence import WorkflowSessionStateRecord, workflow_database
from app.services.workflow.uploads.store import workflow_upload_store


class WorkflowSessionStore:
    """数据库驱动的工作流 session 存储。"""

    def __init__(self) -> None:
        self._lock = RLock()

    def create_session(self, session_id: str | None = None) -> WorkflowSessionState:
        """创建一个新 session；若传入已存在的 session_id，则返回现有 session。"""
        normalized_session_id = self._normalize_session_id(session_id) or uuid4().hex
        with self._lock, workflow_database.session() as session:
            record = session.get(WorkflowSessionStateRecord, normalized_session_id)
            if record is None:
                record = self._new_record(normalized_session_id)
                session.add(record)
            record.updated_at = self._now()
            return self._record_to_state(record)

    def get_session(self, session_id: str | None) -> WorkflowSessionState | None:
        """读取一个 session 的状态快照。"""
        normalized_session_id = self._normalize_session_id(session_id)
        if not normalized_session_id:
            return None

        with self._lock, workflow_database.session() as session:
            record = session.get(WorkflowSessionStateRecord, normalized_session_id)
            if record is None:
                return None
            record.updated_at = self._now()
            return self._record_to_state(record)

    def merge_uploaded_documents(
        self,
        session_id: str,
        documents: list[WorkflowDocument],
    ) -> list[WorkflowDocument]:
        """把新上传文档合并进 session，并返回合并后的完整文档列表。"""
        with self._lock, workflow_database.session() as session:
            record = self._get_or_create_record(session, session_id)
            current_state = self._record_to_state(record)
            previous_tokens = self._collect_upload_tokens(current_state.documents)
            current_state.documents = self._merge_documents(current_state.documents, documents)
            current_state.updatedAt = self._now()
            self._apply_state_to_record(record, current_state)
            self._cleanup_replaced_tokens(previous_tokens, current_state.documents)
            return [document.model_copy(deep=True) for document in current_state.documents]

    def save_plan_response(
        self,
        *,
        session_id: str,
        request: WorkflowRunRequest,
        response: WorkflowPlanResponse,
    ) -> WorkflowSessionState:
        """保存最新规划结果，并刷新 session 的当前输入状态。"""
        with self._lock, workflow_database.session() as session:
            record = self._get_or_create_record(session, session_id)
            state = self._record_to_state(record)
            self._apply_request_to_state(state, request)
            state.latestPlanResponse = response.model_copy(deep=True)
            state.latestExecutionResponse = None
            state.updatedAt = self._now()
            self._apply_state_to_record(record, state)
            return state

    def save_execution_response(
        self,
        *,
        session_id: str,
        request: WorkflowRunRequest,
        plan_response: WorkflowPlanResponse,
        response: WorkflowExecuteResponse,
    ) -> WorkflowSessionState:
        """保存最新执行结果，并同步当前输入状态。"""
        with self._lock, workflow_database.session() as session:
            record = self._get_or_create_record(session, session_id)
            state = self._record_to_state(record)
            self._apply_request_to_state(state, request)
            state.latestPlanResponse = plan_response.model_copy(deep=True)
            state.latestExecutionResponse = response.model_copy(deep=True)
            state.updatedAt = self._now()
            self._apply_state_to_record(record, state)
            return state

    def set_latest_job_id(self, session_id: str, job_id: str | None) -> None:
        """保存该 session 最近一次触发的后台作业。"""
        with self._lock, workflow_database.session() as session:
            record = self._get_or_create_record(session, session_id)
            record.latest_job_id = str(job_id or "").strip() or None
            record.updated_at = self._now()

    def clear_session(self, session_id: str | None) -> bool:
        """删除一个 session。"""
        normalized_session_id = self._normalize_session_id(session_id)
        if not normalized_session_id:
            return False

        with self._lock, workflow_database.session() as session:
            record = session.get(WorkflowSessionStateRecord, normalized_session_id)
            if record is None:
                return False
            state = self._record_to_state(record)
            self._cleanup_tokens(self._collect_upload_tokens(state.documents))
            session.delete(record)
            return True

    def _record_to_state(self, record: WorkflowSessionStateRecord) -> WorkflowSessionState:
        return WorkflowSessionState(
            sessionId=record.session_id,
            createdAt=record.created_at,
            updatedAt=record.updated_at,
            task=record.task,
            documents=[WorkflowDocument.model_validate(item) for item in record.documents_json or []],
            manualConfirm=record.manual_confirm,
            agentMode=record.agent_mode,
            localFallbackEnabled=record.local_fallback_enabled,
            preferredSkills=list(record.preferred_skills or []),
            context=(record.context_json or {}),
            latestPlanResponse=(
                WorkflowPlanResponse.model_validate(record.latest_plan_response_json)
                if record.latest_plan_response_json
                else None
            ),
            latestExecutionResponse=(
                WorkflowExecuteResponse.model_validate(record.latest_execution_response_json)
                if record.latest_execution_response_json
                else None
            ),
            latestJobId=record.latest_job_id,
        )

    def _apply_state_to_record(
        self,
        record: WorkflowSessionStateRecord,
        state: WorkflowSessionState,
    ) -> None:
        record.task = state.task
        record.documents_json = [document.model_dump(mode="json") for document in state.documents]
        record.manual_confirm = state.manualConfirm
        record.agent_mode = state.agentMode
        record.local_fallback_enabled = state.localFallbackEnabled
        record.preferred_skills = list(state.preferredSkills)
        record.context_json = state.context.model_dump(mode="json")
        record.latest_plan_response_json = (
            state.latestPlanResponse.model_dump(mode="json") if state.latestPlanResponse else None
        )
        record.latest_execution_response_json = (
            state.latestExecutionResponse.model_dump(mode="json") if state.latestExecutionResponse else None
        )
        record.latest_job_id = state.latestJobId
        record.updated_at = state.updatedAt

    def _apply_request_to_state(self, state: WorkflowSessionState, request: WorkflowRunRequest) -> None:
        previous_tokens = self._collect_upload_tokens(state.documents)
        state.task = request.task
        state.documents = [document.model_copy(deep=True) for document in request.documents]
        state.manualConfirm = request.manualConfirm
        state.agentMode = request.agentMode
        state.localFallbackEnabled = request.localFallbackEnabled
        state.preferredSkills = list(request.preferredSkills)
        state.context = request.context.model_copy(deep=True)
        self._cleanup_replaced_tokens(previous_tokens, state.documents)

    def _merge_documents(
        self,
        existing_documents: list[WorkflowDocument],
        incoming_documents: list[WorkflowDocument],
    ) -> list[WorkflowDocument]:
        merged = [document.model_copy(deep=True) for document in existing_documents]

        for incoming_document in incoming_documents:
            incoming_copy = incoming_document.model_copy(deep=True)
            index = next(
                (
                    position
                    for position, existing_document in enumerate(merged)
                    if existing_document.name == incoming_copy.name
                    and (existing_document.source or "") == (incoming_copy.source or "")
                ),
                -1,
            )
            if index >= 0:
                merged[index] = incoming_copy
            else:
                merged.append(incoming_copy)

        return merged

    def _collect_upload_tokens(self, documents: list[WorkflowDocument]) -> set[str]:
        return {
            str(document.structuredData.get("workbookUploadToken") or "").strip()
            for document in documents
            if str(document.structuredData.get("workbookUploadToken") or "").strip()
        }

    def _cleanup_replaced_tokens(
        self,
        previous_tokens: set[str],
        current_documents: list[WorkflowDocument],
    ) -> None:
        current_tokens = self._collect_upload_tokens(current_documents)
        self._cleanup_tokens(previous_tokens - current_tokens)

    def _cleanup_tokens(self, tokens: set[str]) -> None:
        for token in tokens:
            workflow_upload_store.delete_bytes(token)

    def _get_or_create_record(
        self,
        session,
        session_id: str | None,
    ) -> WorkflowSessionStateRecord:
        normalized_session_id = self._normalize_session_id(session_id) or uuid4().hex
        record = session.get(WorkflowSessionStateRecord, normalized_session_id)
        if record is None:
            record = self._new_record(normalized_session_id)
            session.add(record)
        record.updated_at = self._now()
        return record

    def _normalize_session_id(self, session_id: str | None) -> str:
        return str(session_id or "").strip()

    def _new_record(self, session_id: str) -> WorkflowSessionStateRecord:
        now = self._now()
        return WorkflowSessionStateRecord(
            session_id=session_id,
            task="",
            manual_confirm=False,
            agent_mode="auto",
            local_fallback_enabled=True,
            preferred_skills=[],
            context_json={},
            documents_json=[],
            latest_plan_response_json=None,
            latest_execution_response_json=None,
            latest_job_id=None,
            created_at=now,
            updated_at=now,
        )

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)


workflow_session_store = WorkflowSessionStore()
