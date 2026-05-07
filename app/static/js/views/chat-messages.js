import {
  READINESS_LABELS,
  STATUS_LABELS,
  mapConfirmationType,
  mapDocumentKinds,
  mapIntentNames,
  mapSkillName,
  mapSkillNames,
} from "../config/labels.js"
import {
  readApprovalContext,
  readConfirmationType,
  readTableMappingPreview,
} from "./confirmation-panel.js?v=20260507-confirm-button"

function summarizeDocumentNames(documents, limit = 4) {
  if (!Array.isArray(documents) || !documents.length) {
    return "暂无材料"
  }

  const names = documents
    .map((documentItem) => String(documentItem.name || "").trim())
    .filter(Boolean)

  if (!names.length) {
    return `${documents.length} 份材料`
  }

  const visible = names.slice(0, limit).join("、")
  return names.length > limit ? `${visible} 等 ${names.length} 份材料` : visible
}

function truncateForChat(text, limit = 260) {
  const normalized = String(text || "").trim()
  if (!normalized) {
    return ""
  }

  return normalized.length > limit ? `${normalized.slice(0, limit - 1)}...` : normalized
}

export function createChatMessageFactory({ state, form }) {
  function summarizePlanSteps(plan, limit = 4) {
    if (!Array.isArray(plan) || !plan.length) {
      return []
    }

    return plan.slice(0, limit).map((step) => {
      const suffix = step.skill ? `：${mapSkillName(step.skill)}` : step.checkpoint ? "：人工确认" : ""
      return `${step.stepNumber}. ${step.title}${suffix}`
    })
  }

  function buildPlanChatMessage(data) {
    const preparedDocuments = data.preparedDocuments || []
    const recommendedSkills = (data.suggestedSkills || []).map((skill) => skill.title).join("、") || mapSkillNames(data.intention && data.intention.recommendedSkills)
    const approvalRequired = Array.isArray(data.plan) && data.plan.some((step) => step.checkpoint === "approval")
    const approvalContext = readApprovalContext(data)
    const intention = data.intention || {}
    const detectedIntentTypes = intention.detectedIntentTypes || (intention.intentType ? [intention.intentType] : [])
    const planSteps = summarizePlanSteps(data.plan)
    const documentSummary = summarizeDocumentNames(preparedDocuments.length ? preparedDocuments : form.readDocuments())
    const payload = state.data.latestPayload || {}
    const header = data.status === "needs_documents"
      ? "我已经看过当前任务和材料，但现在还不能直接执行。"
      : "我已经理解你的需求，并整理好了这轮执行计划。"
    const sections = [
      header,
      [
        `任务理解：${intention.primaryGoal || form.readTask() || "未识别"}`,
        `识别意图：${mapIntentNames(detectedIntentTypes)}`,
        `当前材料：${documentSummary}`,
        `本地回退：${payload.localFallbackEnabled === false ? "关闭" : "开启"}`,
        `推荐能力：${recommendedSkills || "系统暂无推荐技能"}`,
      ].join("\n"),
    ]

    if (data.status === "needs_documents") {
      const missingDocuments = data.missingDocuments || {}
      const missingKindsLabel = mapDocumentKinds(missingDocuments.missingKinds || [])
      const missingKinds = missingKindsLabel === "-" ? "未明确" : missingKindsLabel
      sections.push([
        "目前缺口：",
        `- 还缺少这些材料：${missingKinds}`,
        `- 当前就绪度：${READINESS_LABELS[missingDocuments.readiness] || missingDocuments.readiness || "-"}`,
      ].join("\n"))
      if (missingDocuments.advice && missingDocuments.advice.length) {
        sections.push([
          "建议你下一步这样做：",
          ...missingDocuments.advice.map((item) => `- ${item}`),
        ].join("\n"))
      }
      sections.push("你可以继续上传文件，或者直接告诉我是否先基于现有材料做初步判断。")
      return {
        title: "ESG Agent",
        body: sections.join("\n\n"),
        tone: "warning",
      }
    }

    if (planSteps.length) {
      sections.push(["我建议按下面的顺序处理：", ...planSteps.map((step) => `- ${step}`)].join("\n"))
    }

    if (data.summary) {
      sections.push(`计划说明：${data.summary}`)
    }

    if (approvalRequired) {
      sections.push([
        `确认点：${mapConfirmationType(approvalContext.confirmationType || "plan_review")}`,
        approvalContext.reason || "执行前需要你确认一次，我再继续跑后续步骤。",
        approvalContext.guidance || "",
      ].filter(Boolean).join("\n"))
    }
    sections.push("如果你确认，就直接回复“确认执行”，我会继续处理并把结果像聊天回复一样返回给你。")
    return {
      title: "ESG Agent",
      body: sections.join("\n\n"),
      actions: [
        { label: "确认执行", action: "confirm_execute", variant: "primary" },
      ],
    }
  }

  function buildExecuteChatMessage(data) {
    const executedSkills = mapSkillNames(data.executedSkills || [])
    const finalOutput = data.finalOutput || {}
    const evidenceItems = Array.isArray(finalOutput.evidence) ? finalOutput.evidence : []
    const payload = state.data.latestPayload || {}
    const sections = [
      "这轮处理已经完成。",
      [
        `执行状态：${STATUS_LABELS[data.status] || data.status}`,
        `已执行能力：${executedSkills || "-"}`,
        `本地回退：${payload.localFallbackEnabled === false ? "关闭" : "开启"}`,
      ].join("\n"),
      `结果结论：${finalOutput.summaryText || "执行完成，详细结果已整理到右侧面板。"}`,
    ]

    if (finalOutput.revisedDocument) {
      sections.push(`修订稿预览：${truncateForChat(finalOutput.revisedDocument, 220)}`)
    }

    if (evidenceItems.length) {
      sections.push([
        "依据出处：",
        ...evidenceItems.slice(0, 2).map((item) => `- ${item.document} / ${item.location}：${truncateForChat(item.excerpt, 80)}`),
      ].join("\n"))
    }

    if (Array.isArray(finalOutput.downloads) && finalOutput.downloads.length) {
      sections.push([
        "导出文件：",
        ...finalOutput.downloads.map((item) => `- ${item.filename}`),
      ].join("\n"))
    }

    const artifactKeys = Object.keys(finalOutput.artifacts || {})
    if (artifactKeys.length) {
      sections.push([
        "这次还生成了这些结构化结果：",
        ...artifactKeys.slice(0, 6).map((key) => `- ${key}`),
      ].join("\n"))
    }

    if (finalOutput.nextActions && finalOutput.nextActions.length) {
      sections.push([
        "建议你下一步继续：",
        ...finalOutput.nextActions.map((item) => `- ${item}`),
      ].join("\n"))
    }
    sections.push("如果你要我继续细化摘要、改写措辞、补一版董事会口径，直接在对话里继续说。")

    return {
      title: "ESG Agent",
      body: sections.join("\n\n"),
    }
  }

  function buildAwaitingConfirmationChatMessage(data) {
    const hasTableMappingPreview = Boolean(readTableMappingPreview((data || {}).finalOutput))
    const approvalContext = readApprovalContext(data)
    const confirmationType = readConfirmationType(data)
    const reason = String(approvalContext.reason || "").trim()
    const guidance = String(approvalContext.guidance || "").trim()
    const genericBody = [
      `后台作业已运行到待确认节点：${mapConfirmationType(confirmationType)}。`,
      reason,
      guidance || "请检查右侧的任务理解、执行计划、日志和当前输出；确认无误后回复“确认执行”。",
    ].filter(Boolean).join("\n\n")

    return {
      title: "ESG Agent",
      body: hasTableMappingPreview
        ? "后台作业已运行到待确认节点。人工确认面板展示了自动识别的表格映射，你可以先修改，再回复“确认执行”。"
        : `${genericBody}\n\n确认后继续执行后续步骤。`,
      actions: [
        { label: "确认执行", action: "confirm_execute", variant: "primary" },
      ],
    }
  }

  return {
    buildPlanChatMessage,
    buildExecuteChatMessage,
    buildAwaitingConfirmationChatMessage,
    buildPlanBlockedMessage: () => ({
      title: "ESG Agent",
      body: "当前上下文还不能规划，请先补充任务描述或修正文档数据。",
      tone: "warning",
    }),
    buildNoExecutablePlanMessage: () => ({
      title: "ESG Agent",
      body: "当前还没有可执行的计划。请先描述任务，或补充文件让我重新规划。",
      tone: "warning",
    }),
    buildTaskContextErrorMessage: () => ({
      title: "ESG Agent",
      body: "任务上下文解析失败，请检查“原始任务与文档”里的任务或文档数据。",
      tone: "error",
    }),
    buildPlanningErrorMessage: (error) => ({
      title: "ESG Agent",
      body: `规划失败：${error.message}`,
      tone: "error",
    }),
    buildExecutionErrorMessage: (error) => ({
      title: "ESG Agent",
      body: `执行失败：${error.message}`,
      tone: "error",
    }),
    buildConversationClearedMessage: () => ({
      title: "ESG Agent",
      body: "当前会话、任务上下文和规划结果都已清空。你可以直接开始描述新的需求。",
    }),
    buildUploadMergedMessage: ({ total, names, warnings }) => {
      const warningLines = warnings && warnings.length
        ? ["上传提示：", ...warnings.slice(0, 3).map((warning) => `- ${warning}`)].join("\n")
        : ""
      return {
        title: "ESG Agent",
        body: [
          `我已经收到 ${total} 份文件。`,
          `当前并入会话的材料：${names || "未命名文件"}`,
          warningLines,
        ].filter(Boolean).join("\n\n"),
      }
    },
    buildUploadAwaitingTaskMessage: () => ({
      title: "ESG Agent",
      body: "文件已经准备好。现在直接在对话框告诉我你想怎么处理这些材料。",
    }),
    buildUploadReplanMessage: () => ({
      title: "ESG Agent",
      body: "我会基于刚上传的材料，重新整理这轮判断和执行计划。",
    }),
  }
}
