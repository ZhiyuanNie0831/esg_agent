"""工作流持久化层。

使用 SQLAlchemy 管理 session/job/artifact 元数据，文件内容仍落本地文件系统。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterator

from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.sql.sqltypes import JSON

from app.config import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """SQLAlchemy 声明基类。"""


class WorkflowSessionStateRecord(Base):
    """持久化后的 session 状态。"""

    __tablename__ = "workflow_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task: Mapped[str] = mapped_column(Text, default="")
    manual_confirm: Mapped[bool] = mapped_column(Boolean, default=True)
    agent_mode: Mapped[str] = mapped_column(String(16), default="auto")
    local_fallback_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    documents_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    latest_plan_response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    latest_execution_response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    latest_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WorkflowJobRecord(Base):
    """后台工作流作业。"""

    __tablename__ = "workflow_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    task: Mapped[str] = mapped_column(Text, default="")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    plan_overrides_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    plan_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    intention_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    prepared_documents_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    missing_documents_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    logs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    executed_skills_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    final_output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    reuse_source_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowArtifactRecord(Base):
    """导出产物元数据。"""

    __tablename__ = "workflow_artifacts"

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    label: Mapped[str] = mapped_column(Text, default="")
    filename: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    relative_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WorkflowDatabase:
    """数据库入口与基础查询能力。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self._engine = self._build_engine()
        self._session_factory = sessionmaker(
            bind=self._engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        self._initialize()

    @property
    def engine(self) -> Engine:
        return self._engine

    @property
    def is_postgres(self) -> bool:
        return self._engine.dialect.name == "postgresql"

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_resumable_job_ids(self) -> list[str]:
        """返回需要重新投入 worker 的作业。"""
        stale_before = _utcnow() - timedelta(seconds=settings.workflow_job_heartbeat_timeout_seconds)
        with self.session() as session:
            stale_running = session.scalars(
                select(WorkflowJobRecord).where(
                    WorkflowJobRecord.status == "running",
                    (WorkflowJobRecord.heartbeat_at.is_(None)) | (WorkflowJobRecord.heartbeat_at < stale_before),
                )
            ).all()
            resumable_ids = [
                record.job_id
                for record in session.scalars(
                    select(WorkflowJobRecord).where(WorkflowJobRecord.status == "queued")
                ).all()
            ]
            for record in stale_running:
                record.status = "queued"
                record.updated_at = _utcnow()
                resumable_ids.append(record.job_id)
            return sorted(dict.fromkeys(resumable_ids))

    def _build_engine(self) -> Engine:
        database_url = settings.database_url
        connect_args: dict[str, Any] = {}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        return create_engine(database_url, connect_args=connect_args)

    def _initialize(self) -> None:
        with self._lock:
            storage_root = Path(settings.workflow_storage_dir)
            storage_root.mkdir(parents=True, exist_ok=True)
            Base.metadata.create_all(self._engine)


workflow_database = WorkflowDatabase()
