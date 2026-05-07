"""工作流错误定义。

把前端需要感知的配置错误和 agent 不可用错误显式化，
避免静默回退导致用户误以为仍在走固定 provider。
"""

from __future__ import annotations


class WorkflowServiceError(RuntimeError):
    """工作流服务可预期错误。"""

    status_code = 400


class WorkflowConfigurationError(WorkflowServiceError):
    """请求配置本身不合法。"""


class WorkflowAgentUnavailableError(WorkflowServiceError):
    """请求要求 agent，但当前没有 agent 结果且不允许本地回退。"""

    status_code = 503


def require_local_fallback(
    *,
    local_fallback_enabled: bool,
    agent_active: bool,
    capability: str,
) -> None:
    """当本地回退被禁用时，显式抛出 agent 不可用错误。"""
    if local_fallback_enabled:
        return

    if agent_active:
        raise WorkflowAgentUnavailableError(
            f"模型 API agent 未返回有效的{capability}结果，且已关闭本地回退。"
        )

    raise WorkflowAgentUnavailableError(
        f"当前未启用模型 API agent，且已关闭本地回退，无法执行{capability}。"
    )
