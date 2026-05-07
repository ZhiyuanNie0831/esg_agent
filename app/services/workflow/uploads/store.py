"""上传文件原件存储。

原始二进制内容落本地文件系统，返回 token 供后续 Excel 回填复用。
"""

from __future__ import annotations

from app.services.workflow.file_store import workflow_file_store


class WorkflowUploadStore:
    """上传原件访问包装层。"""

    def put_bytes(self, data: bytes, *, filename: str = "upload.bin") -> str:
        """写入文件字节并返回访问 token。"""
        return workflow_file_store.put_upload_bytes(data, filename=filename)

    def get_bytes(self, token: str | None) -> bytes | None:
        """按 token 读取文件字节。"""
        return workflow_file_store.get_upload_bytes(token)

    def delete_bytes(self, token: str | None) -> None:
        """按 token 删除缓存的文件字节。"""
        workflow_file_store.delete_upload_bytes(token)


workflow_upload_store = WorkflowUploadStore()
