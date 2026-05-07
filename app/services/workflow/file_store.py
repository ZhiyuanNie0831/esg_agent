"""工作流文件存储。

上传原件和导出产物写入本地文件系统，产物元数据同时持久化到数据库。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.config import settings
from app.services.workflow.persistence import WorkflowArtifactRecord, workflow_database


class WorkflowFileStore:
    """管理上传原件与导出产物的本地文件存储。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self._root = Path(settings.workflow_storage_dir)
        self._uploads_dir = self._root / "uploads"
        self._artifacts_dir = self._root / "artifacts"
        self._uploads_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

    def put_upload_bytes(self, data: bytes, *, filename: str = "upload.bin") -> str:
        """写入上传原件并返回访问 token。"""
        token = uuid4().hex
        target_dir = self._uploads_dir / token
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / self._safe_filename(filename)
        target_path.write_bytes(data)
        return token

    def get_upload_bytes(self, token: str | None) -> bytes | None:
        """按 token 读取上传原件。"""
        if not token:
            return None
        target_dir = self._uploads_dir / str(token).strip()
        if not target_dir.exists():
            return None
        files = [path for path in target_dir.iterdir() if path.is_file()]
        if not files:
            return None
        return files[0].read_bytes()

    def delete_upload_bytes(self, token: str | None) -> None:
        """删除一个上传原件 token 对应的数据。"""
        if not token:
            return
        target_dir = self._uploads_dir / str(token).strip()
        if not target_dir.exists():
            return
        for path in target_dir.iterdir():
            if path.is_file():
                path.unlink(missing_ok=True)
        target_dir.rmdir()

    def store_artifact(
        self,
        *,
        job_id: str | None,
        label: str,
        filename: str,
        mime_type: str,
        data: bytes,
    ) -> dict[str, object]:
        """写入导出产物，并返回前端可直接使用的下载元数据。"""
        artifact_id = uuid4().hex
        sha256 = hashlib.sha256(data).hexdigest()
        safe_filename = self._safe_filename(filename)
        target_dir = self._artifacts_dir / artifact_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe_filename
        target_path.write_bytes(data)
        relative_path = str(target_path.relative_to(self._root))

        with workflow_database.session() as session:
            session.merge(
                WorkflowArtifactRecord(
                    artifact_id=artifact_id,
                    job_id=job_id,
                    label=label,
                    filename=filename,
                    mime_type=mime_type,
                    relative_path=relative_path,
                    size_bytes=len(data),
                    sha256=sha256,
                )
            )

        return {
            "artifactId": artifact_id,
            "label": label,
            "filename": filename,
            "mimeType": mime_type,
            "downloadUrl": f"/api/workflow/artifacts/{artifact_id}",
        }

    def read_artifact(self, artifact_id: str) -> tuple[WorkflowArtifactRecord | None, bytes | None]:
        """读取导出产物元数据与内容。"""
        with workflow_database.session() as session:
            record = session.get(WorkflowArtifactRecord, artifact_id)
            if record is None:
                return None, None
            target_path = self._root / record.relative_path
            if not target_path.exists():
                return record, None
            return record, target_path.read_bytes()

    def _safe_filename(self, filename: str) -> str:
        normalized = os.path.basename(str(filename or "").strip()) or "file.bin"
        return normalized.replace("/", "_").replace("\\", "_")


workflow_file_store = WorkflowFileStore()

