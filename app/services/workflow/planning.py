"""执行计划生成服务。

根据意图分析结果、缺失材料情况和推荐技能，生成可执行的工作流步骤。
"""

from app.schemas.workflow import (
    IntentionAnalysis,
    MissingDocumentCheck,
    PlanStep,
    PreparedDocument,
    SkillDescriptor,
    WorkflowPlanStatus,
)
from app.services.workflow.skills.registry import WorkflowSkillRegistry
from app.services.workflow.text import intent_label, join_document_kind_labels, join_intent_labels


class WorkflowPlanningService:
    """把分析结果转换成可执行计划。"""

    def build_plan(
        self,
        task: str,
        documents: list[PreparedDocument],
        intention: IntentionAnalysis,
        missing_documents: MissingDocumentCheck,
        skill_registry: WorkflowSkillRegistry,
        manual_confirm: bool,
    ) -> tuple[WorkflowPlanStatus, list[SkillDescriptor], list[PlanStep], str]:
        """构造执行计划、推荐技能列表和规划摘要。"""
        suggested_skills = [
            skill_registry.require(skill_name).descriptor()
            for skill_name in intention.recommendedSkills
            if skill_registry.get(skill_name) is not None
        ]
        planned_skills = self._build_planned_skills(
            suggested_skills=suggested_skills,
            skill_registry=skill_registry,
            manual_confirm=manual_confirm,
        )
        plan_steps: list[PlanStep] = [
            PlanStep(
                stepNumber=1,
                title="检查输入材料",
                description=self._build_input_review_description(task),
                outputs=["标准化文档清单", "意图分析结果"],
            )
        ]

        if missing_documents.missingKinds:
            plan_steps.append(
                PlanStep(
                    stepNumber=2,
                    title="补齐缺失材料",
                    description=(
                        f"当前问题还不能直接回答，需要先补齐这些材料："
                        f"{join_document_kind_labels(missing_documents.missingKinds)}。"
                    ),
                    status="blocked",
                    dependsOn=[1],
                    outputs=["待补齐材料清单"],
                )
            )
            plan_steps = self._assign_step_ids(plan_steps)
            summary_parts = [
                f"当前任务被识别为“{intent_label(intention.intentType)}”流程。",
                "由于存在缺失材料，执行暂时被阻塞。",
            ]
            if missing_documents.advice:
                summary_parts.append("下一步建议：" + "；".join(missing_documents.advice))
            summary = "".join(summary_parts)
            return "needs_documents", suggested_skills, plan_steps, summary

        next_step_number = 2
        previous_step_number = 1
        approval_inserted = False
        approval_reason = self._build_approval_reason(manual_confirm, suggested_skills)
        approval_before_skill = self._resolve_approval_before_skill(planned_skills, approval_reason)
        approval_context = self._build_approval_context(
            planned_skills=planned_skills,
            approval_reason=approval_reason,
            approval_before_skill=approval_before_skill,
        )
        for skill in planned_skills:
            if approval_reason and not approval_inserted:
                should_insert_approval = approval_before_skill is None or skill.name == approval_before_skill
            else:
                should_insert_approval = False

            if should_insert_approval:
                plan_steps.append(
                    PlanStep(
                        stepNumber=next_step_number,
                        title=self._build_approval_step_title(approval_context),
                        description=self._build_approval_step_description(approval_context),
                        checkpoint="approval",
                        requiresApproval=True,
                        dependsOn=[previous_step_number],
                        outputs=[str(approval_context.get("outputLabel") or "审批结果")],
                        inputs=approval_context,
                    )
                )
                previous_step_number = next_step_number
                next_step_number += 1
                approval_inserted = True

            plan_steps.append(
                PlanStep(
                    stepNumber=next_step_number,
                    title=skill.title,
                    description=self._build_skill_step_description(
                        task=task,
                        intention=intention,
                        skill=skill,
                    ),
                    skill=skill.name,
                    requiresApproval=skill.requiresApproval,
                    dependsOn=[previous_step_number],
                    outputs=[skill.outputHint] if skill.outputHint else [],
                    inputs={
                        "documentCount": len(documents),
                        "intentType": intention.intentType,
                        "detectedIntentTypes": intention.detectedIntentTypes,
                    },
                )
            )
            previous_step_number = next_step_number
            next_step_number += 1

        plan_steps.append(
            PlanStep(
                stepNumber=next_step_number,
                title="整理最终输出",
                description="把各步骤结果整理成直接回答当前问题的结论，并附上关键出处；如有修订稿会一并输出。",
                dependsOn=[previous_step_number],
                outputs=["最终总结", "结构化产物", "可选修订稿"],
            )
        )
        plan_steps = self._assign_step_ids(plan_steps)

        summary_parts = [
            f"当前任务被识别为“{intent_label(intention.intentType)}”流程，",
            f"共识别 {len(intention.detectedIntentTypes)} 个意图：{join_intent_labels(intention.detectedIntentTypes)}。",
            f"共有 {len(documents)} 份已处理文档，推荐 {len(suggested_skills)} 个技能步骤。",
        ]
        if approval_inserted:
            summary_parts.append("执行前需要人工确认。")
        if missing_documents.advice:
            summary_parts.append("注意事项：" + "；".join(missing_documents.advice))
        summary = "".join(summary_parts)
        return "ready_to_execute", suggested_skills, plan_steps, summary

    def _assign_step_ids(self, plan_steps: list[PlanStep]) -> list[PlanStep]:
        """为同一份计划生成稳定的步骤 ID，便于审批后继续复用覆写。"""
        assigned_steps: list[PlanStep] = []
        used_ids: set[str] = set()

        for step in plan_steps:
            kind = step.skill or step.checkpoint or "system"
            base_step_id = f"step_{step.stepNumber}_{kind}"
            step_id = base_step_id
            suffix = 2
            while step_id in used_ids:
                step_id = f"{base_step_id}_{suffix}"
                suffix += 1
            used_ids.add(step_id)
            assigned_steps.append(step.model_copy(update={"stepId": step_id}))

        return assigned_steps

    def _build_planned_skills(
        self,
        *,
        suggested_skills: list[SkillDescriptor],
        skill_registry: WorkflowSkillRegistry,
        manual_confirm: bool,
    ) -> list[SkillDescriptor]:
        """在推荐技能的基础上补全 Excel 计算和填表 workflow 步骤。"""
        planned_skills = [skill.model_copy(deep=True) for skill in suggested_skills]
        skill_names = [skill.name for skill in planned_skills]
        if "spreadsheet_calculator" not in skill_names:
            if "table_data_transfer" not in skill_names:
                return planned_skills
            planned_skills = self._insert_skill_before(
                planned_skills=planned_skills,
                skill_registry=skill_registry,
                skill_name="excel_role_classifier",
                before_skill="table_data_transfer",
            )
            return planned_skills

        planned_skills = self._insert_skill_before(
            planned_skills=planned_skills,
            skill_registry=skill_registry,
            skill_name="calculation_planner",
            before_skill="spreadsheet_calculator",
        )
        skill_names = [skill.name for skill in planned_skills]
        if "table_filler" not in skill_names:
            return planned_skills

        role_classifier_before = "calculation_planner" if "calculation_planner" in skill_names else "spreadsheet_calculator"
        planned_skills = self._insert_skill_before(
            planned_skills=planned_skills,
            skill_registry=skill_registry,
            skill_name="excel_role_classifier",
            before_skill=role_classifier_before,
        )
        planned_skills = self._insert_skill_before(
            planned_skills=planned_skills,
            skill_registry=skill_registry,
            skill_name="table_mapping_preview",
            before_skill="table_filler",
        )
        planned_skills = self._insert_skill_after(
            planned_skills=planned_skills,
            skill_registry=skill_registry,
            skill_name="fill_validator",
            after_skill="table_filler",
        )
        return planned_skills

    def _insert_skill_before(
        self,
        *,
        planned_skills: list[SkillDescriptor],
        skill_registry: WorkflowSkillRegistry,
        skill_name: str,
        before_skill: str,
    ) -> list[SkillDescriptor]:
        skill_names = [skill.name for skill in planned_skills]
        skill = skill_registry.get(skill_name)
        if skill is None or skill_name in skill_names or before_skill not in skill_names:
            return planned_skills
        planned_skills.insert(skill_names.index(before_skill), skill.descriptor())
        return planned_skills

    def _insert_skill_after(
        self,
        *,
        planned_skills: list[SkillDescriptor],
        skill_registry: WorkflowSkillRegistry,
        skill_name: str,
        after_skill: str,
    ) -> list[SkillDescriptor]:
        skill_names = [skill.name for skill in planned_skills]
        skill = skill_registry.get(skill_name)
        if skill is None or skill_name in skill_names or after_skill not in skill_names:
            return planned_skills
        planned_skills.insert(skill_names.index(after_skill) + 1, skill.descriptor())
        return planned_skills

    def _resolve_approval_before_skill(
        self,
        planned_skills: list[SkillDescriptor],
        approval_reason: str,
    ) -> str | None:
        """决定审批检查点应放在第一个技能前，还是放到填表预览之后。"""
        if not approval_reason:
            return None
        skill_names = [skill.name for skill in planned_skills]
        if "table_mapping_preview" in skill_names and "table_filler" in skill_names:
            return "table_filler"
        if "esg_report_outline_builder" in skill_names and "esg_report_writer" in skill_names:
            return "esg_report_writer"
        return planned_skills[0].name if planned_skills else None

    def _build_approval_context(
        self,
        *,
        planned_skills: list[SkillDescriptor],
        approval_reason: str,
        approval_before_skill: str | None,
    ) -> dict[str, object]:
        skill_names = [skill.name for skill in planned_skills]
        approval_required_skills = [
            {"name": skill.name, "title": skill.title}
            for skill in planned_skills
            if skill.requiresApproval
        ]
        if "table_mapping_preview" in skill_names and "table_filler" in skill_names:
            confirmation_type = "table_mapping"
            title = "确认填表映射"
            output_label = "填表映射确认结果"
            guidance = "先审阅候选 sheet、单元格、写入策略和低置信度风险，再继续写入模板。"
        elif "esg_report_outline_builder" in skill_names and "esg_report_writer" in skill_names:
            confirmation_type = "esg_report_generation"
            title = "确认 ESG 报告生成"
            output_label = "ESG 报告生成确认结果"
            guidance = "先审阅披露矩阵、报告大纲、证据链接和客户字数要求，再继续生成报告正文。"
        elif approval_required_skills:
            confirmation_type = "risk_step"
            title = "确认高影响步骤"
            output_label = "高影响步骤确认结果"
            guidance = "先审阅计划和当前预览结果，再继续执行会改写、写入或生成正式输出的步骤。"
        else:
            confirmation_type = "plan_review"
            title = "确认执行计划"
            output_label = "计划确认结果"
            guidance = "先审阅任务理解、输入材料和执行计划，再继续执行后续步骤。"

        return {
            "mode": "manual_confirmation",
            "confirmationType": confirmation_type,
            "title": title,
            "reason": approval_reason,
            "guidance": guidance,
            "beforeSkill": approval_before_skill,
            "approvalRequiredSkills": approval_required_skills,
            "outputLabel": output_label,
        }

    def _build_approval_step_title(self, approval_context: dict[str, object]) -> str:
        return str(approval_context.get("title") or "人工确认")

    def _build_approval_step_description(self, approval_context: dict[str, object]) -> str:
        reason = str(approval_context.get("reason") or "").strip()
        guidance = str(approval_context.get("guidance") or "").strip()
        parts = [part for part in (reason, guidance, "确认后将继续按当前任务执行后续步骤。") if part]
        return "".join(parts)

    def _build_approval_reason(
        self,
        manual_confirm: bool,
        suggested_skills: list[SkillDescriptor],
    ) -> str:
        """生成需要人工确认的原因说明。"""
        approval_required_skills = [skill.title for skill in suggested_skills if skill.requiresApproval]

        if approval_required_skills:
            return (
                "当前计划包含需要人工确认的步骤："
                f"{'、'.join(approval_required_skills)}。"
            )
        if manual_confirm:
            return "当前流程启用了人工确认，执行前需要先审核计划和输入材料。"

        return ""

    def _build_input_review_description(self, task: str) -> str:
        """生成“检查输入材料”步骤的描述。"""
        task_snippet = self._clip_task(task)
        return f"先确认当前要回答的问题是“{task_snippet}”，并核对已上传材料是否足够支持后续判断。"

    def _build_skill_step_description(
        self,
        *,
        task: str,
        intention: IntentionAnalysis,
        skill: SkillDescriptor,
    ) -> str:
        """根据技能类型生成更贴近当前任务的步骤描述。"""
        task_snippet = self._clip_task(task)
        intent_text = intent_label(intention.intentType)
        output_hint = skill.outputHint or "结果"

        description_map = {
            "document_reader": f"围绕“{task_snippet}”先读取并定位相关材料片段，为后续结论保留出处。",
            "document_counter": f"统计与“{task_snippet}”相关的材料数量和类别，确认输入范围是否完整。",
            "document_summarizer": f"提炼与“{task_snippet}”直接相关的重点内容，并保留可引用的材料位置。",
            "document_reviser": f"根据当前任务把原始材料整理成更清晰的草稿，同时保留关键依据。",
            "esg_material_checker": f"核对 ESG 材料是否足以回答“{task_snippet}”，并识别缺口所在。",
            "esg_standard_selector": f"根据“{task_snippet}”选择报告应对齐的 ESG 标准体系，明确后续披露基准。",
            "esg_disclosure_mapper": f"把现有材料映射到 ESG 披露主题，确认哪些主题已经被当前问题覆盖。",
            "esg_disclosure_matrix_builder": f"把披露标准、主题覆盖、证据强弱和缺口整理成可审阅的 ESG 披露矩阵。",
            "esg_kpi_extractor": f"从材料中抽取与“{task_snippet}”相关的指标，并标明来源片段。",
            "esg_data_request_builder": f"把披露缺口转成面向业务部门的补资料和追数清单。",
            "esg_evidence_linker": f"为披露主题和 KPI 建立 claim 到原始材料位置的证据索引。",
            "esg_report_outline_builder": f"基于现有材料生成能回应当前问题的 ESG 大纲，并标注关键依据方向。",
            "esg_report_writer": f"根据“{task_snippet}”的客户字数要求、披露矩阵、KPI 和证据索引生成 ESG 报告正文草稿。",
            "excel_role_classifier": f"先判断哪些 Excel 是源数据、哪些是待填模板，为后续计算和写入建立清晰输入边界。",
            "calculation_planner": f"把“{task_snippet}”转换为结构化计算计划，明确要算的 sheet、字段、操作和分组。",
            "spreadsheet_calculator": f"按任务要求计算表格中的关键数值，并保留工作表和字段来源。",
            "table_mapping_preview": f"先根据模板自动预估填表位置，生成待确认的候选 sheet 和单元格。",
            "table_filler": f"按已确认或自动识别的映射写入模板 Excel，并记录逐单元格审计。",
            "table_data_transfer": f"按目标表表头匹配源表列，把“{task_snippet}”涉及的源表明细自动写入目标 Excel。",
            "fill_validator": f"重新读取已导出的 Excel，校验目标单元格是否和计算结果一致。",
        }
        default_description = (
            f"执行“{skill.title}”来支持当前{intent_text}任务“{task_snippet}”，"
            f"输出{output_hint}。"
        )
        return description_map.get(skill.name, default_description)

    def _clip_task(self, task: str, limit: int = 42) -> str:
        """裁剪任务描述，避免计划文案过长。"""
        normalized = " ".join(str(task or "").split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: limit - 1]}…"
