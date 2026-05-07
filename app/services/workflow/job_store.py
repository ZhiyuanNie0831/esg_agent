"""后台作业存储。"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from app.schemas.workflow import WorkflowJobSnapshot
from app.services.workflow.persistence import WorkflowJobRecord, workflow_database


class WorkflowJobStore:
    """SQL 驱动的后台作业快照存储。"""

    def __init__(self) -> None:
        self._lock = RLock()

    def create(self, snapshot: WorkflowJobSnapshot) -> WorkflowJobSnapshot:
        with self._lock, workflow_database.session() as session:
            record = self._snapshot_to_record(snapshot)
            session.add(record)
            return self._record_to_snapshot(record)

    def get(self, job_id: str) -> WorkflowJobSnapshot | None:
        with self._lock, workflow_database.session() as session:
            record = session.get(WorkflowJobRecord, job_id)
            if record is None:
                return None
            return self._record_to_snapshot(record)

    def save(self, snapshot: WorkflowJobSnapshot) -> WorkflowJobSnapshot:
        with self._lock, workflow_database.session() as session:
            record = session.get(WorkflowJobRecord, snapshot.jobId)
            if record is None:
                record = self._snapshot_to_record(snapshot)
                session.add(record)
            else:
                self._apply_snapshot_to_record(record, snapshot)
            return self._record_to_snapshot(record)

    def touch_heartbeat(self, job_id: str) -> None:
        with self._lock, workflow_database.session() as session:
            record = session.get(WorkflowJobRecord, job_id)
            if record is None:
                return
            now = self._now()
            record.heartbeat_at = now
            record.updated_at = now

    def list_resumable_job_ids(self) -> list[str]:
        return workflow_database.list_resumable_job_ids()

    def _record_to_snapshot(self, record: WorkflowJobRecord) -> WorkflowJobSnapshot:
        return WorkflowJobSnapshot.model_validate(
            {
                "jobId": record.job_id,
                "requestId": record.request_id,
                "sessionId": record.session_id,
                "status": record.status,
                "task": record.task,
                "approved": record.approved,
                "request": record.request_json,
                "planOverrides": record.plan_overrides_json or {},
                "plan": record.plan_json or [],
                "intention": record.intention_json,
                "preparedDocuments": record.prepared_documents_json or [],
                "missingDocuments": record.missing_documents_json,
                "logs": record.logs_json or [],
                "executedSkills": record.executed_skills_json or [],
                "finalOutput": record.final_output_json,
                "error": record.error,
                "createdAt": record.created_at,
                "updatedAt": record.updated_at,
                "completedAt": record.completed_at,
                "reuseSourceJobId": record.reuse_source_job_id,
            }
        )

    def _snapshot_to_record(self, snapshot: WorkflowJobSnapshot) -> WorkflowJobRecord:
        return WorkflowJobRecord(
            job_id=snapshot.jobId or uuid4().hex,
            request_id=str(snapshot.requestId),
            session_id=snapshot.sessionId,
            status=snapshot.status,
            task=snapshot.task,
            approved=snapshot.approved,
            request_json=snapshot.request.model_dump(mode="json"),
            plan_overrides_json=snapshot.planOverrides.model_dump(mode="json"),
            plan_json=[item.model_dump(mode="json") for item in snapshot.plan],
            intention_json=snapshot.intention.model_dump(mode="json") if snapshot.intention else None,
            prepared_documents_json=[item.model_dump(mode="json") for item in snapshot.preparedDocuments],
            missing_documents_json=(
                snapshot.missingDocuments.model_dump(mode="json") if snapshot.missingDocuments else None
            ),
            logs_json=[item.model_dump(mode="json") for item in snapshot.logs],
            executed_skills_json=list(snapshot.executedSkills),
            final_output_json=snapshot.finalOutput.model_dump(mode="json") if snapshot.finalOutput else None,
            error=snapshot.error,
            reuse_source_job_id=snapshot.reuseSourceJobId,
            created_at=snapshot.createdAt,
            updated_at=snapshot.updatedAt,
            completed_at=snapshot.completedAt,
            heartbeat_at=snapshot.updatedAt,
        )

    def _apply_snapshot_to_record(
        self,
        record: WorkflowJobRecord,
        snapshot: WorkflowJobSnapshot,
    ) -> None:
        record.request_id = str(snapshot.requestId)
        record.session_id = snapshot.sessionId
        record.status = snapshot.status
        record.task = snapshot.task
        record.approved = snapshot.approved
        record.request_json = snapshot.request.model_dump(mode="json")
        record.plan_overrides_json = snapshot.planOverrides.model_dump(mode="json")
        record.plan_json = [item.model_dump(mode="json") for item in snapshot.plan]
        record.intention_json = snapshot.intention.model_dump(mode="json") if snapshot.intention else None
        record.prepared_documents_json = [item.model_dump(mode="json") for item in snapshot.preparedDocuments]
        record.missing_documents_json = (
            snapshot.missingDocuments.model_dump(mode="json") if snapshot.missingDocuments else None
        )
        record.logs_json = [item.model_dump(mode="json") for item in snapshot.logs]
        record.executed_skills_json = list(snapshot.executedSkills)
        record.final_output_json = snapshot.finalOutput.model_dump(mode="json") if snapshot.finalOutput else None
        record.error = snapshot.error
        record.reuse_source_job_id = snapshot.reuseSourceJobId
        record.updated_at = snapshot.updatedAt
        record.completed_at = snapshot.completedAt
        record.heartbeat_at = snapshot.updatedAt

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)


workflow_job_store = WorkflowJobStore()

