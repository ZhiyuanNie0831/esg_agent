"""计划覆写工具。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.schemas.workflow import PlanOverrides, PlanStep
from app.services.workflow.errors import WorkflowConfigurationError


def apply_plan_overrides(
    plan: list[PlanStep],
    overrides: PlanOverrides | None,
) -> list[PlanStep]:
    """应用执行前允许的有限计划修改。"""
    if overrides is None:
        return [step.model_copy(deep=True) for step in plan]

    overridden_plan = [step.model_copy(deep=True) for step in plan]
    steps_by_id = {step.stepId: step for step in overridden_plan}

    for step_id in overrides.disabledStepIds:
        step = steps_by_id.get(step_id)
        if step is None:
            raise WorkflowConfigurationError(f"未知 stepId，无法禁用步骤：{step_id}")
        if step.skill is None or step.checkpoint:
            raise WorkflowConfigurationError(f"该步骤不支持禁用：{step.title}")
        step.status = "skipped"

    for step_id, input_override in overrides.stepInputOverrides.items():
        step = steps_by_id.get(step_id)
        if step is None:
            raise WorkflowConfigurationError(f"未知 stepId，无法覆写输入：{step_id}")
        if not isinstance(input_override, dict):
            raise WorkflowConfigurationError(f"stepInputOverrides 必须是对象映射：{step_id}")
        step.inputs = _deep_merge(step.inputs, input_override)

    return overridden_plan


def merge_plan_overrides(base: PlanOverrides, patch: PlanOverrides) -> PlanOverrides:
    """合并已有覆写和审批阶段提交的新覆写。"""
    disabled = list(dict.fromkeys([*base.disabledStepIds, *patch.disabledStepIds]))
    merged_inputs = deepcopy(base.stepInputOverrides)
    for step_id, override in patch.stepInputOverrides.items():
        if step_id in merged_inputs and isinstance(merged_inputs[step_id], dict) and isinstance(override, dict):
            merged_inputs[step_id] = _deep_merge(merged_inputs[step_id], override)
        else:
            merged_inputs[step_id] = deepcopy(override)
    return PlanOverrides(disabledStepIds=disabled, stepInputOverrides=merged_inputs)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
            continue
        merged[key] = deepcopy(value)
    return merged
