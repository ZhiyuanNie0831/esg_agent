import {
  READINESS_LABELS,
  STATUS_LABELS,
  formatCompactJson,
  formatDateTime,
  formatDuration,
  formatList,
  mapConfirmationType,
  mapDocumentKinds,
  mapExecutorLabel,
  mapIntentLabel,
  mapIntentNames,
  mapLogKind,
  mapSkillName,
  mapSkillNames,
} from "../config/labels.js"
import { escapeHtml, renderCards, setHtml, setText } from "../core/html.js"
import { createConfirmationPanel } from "./confirmation-panel.js?v=20260507-confirm-button"
import { createFinalOutputPanel } from "./final-output-panel.js"

function formatLogInputSummary(summary) {
  if (!summary || typeof summary !== "object") {
    return "-"
  }

  const parts = []
  if (typeof summary.documentCount === "number") {
    parts.push(`文档 ${summary.documentCount} 份`)
  }
  if (typeof summary.segmentCount === "number") {
    parts.push(`片段 ${summary.segmentCount} 段`)
  }
  if (Array.isArray(summary.documentNames) && summary.documentNames.length) {
    parts.push(`材料：${summary.documentNames.join("、")}`)
  }
  if (Array.isArray(summary.availablePreviousResults) && summary.availablePreviousResults.length) {
    parts.push(`前序结果：${summary.availablePreviousResults.map((skillName) => mapSkillName(skillName)).join("、")}`)
  }
  if (summary.requiresApproval) {
    parts.push("包含人工确认要求")
  }
  if (summary.planInputs && Object.keys(summary.planInputs).length) {
    parts.push(`计划输入：${formatCompactJson(summary.planInputs)}`)
  }

  return parts.join("；") || "-"
}

function formatLogOutputSummary(summary) {
  if (!summary || typeof summary !== "object") {
    return "-"
  }

  const parts = []
  if (Array.isArray(summary.resultKeys) && summary.resultKeys.length) {
    parts.push(`返回字段：${summary.resultKeys.join("、")}`)
  }
  if (Array.isArray(summary.stepOutputs) && summary.stepOutputs.length) {
    parts.push(`计划输出：${summary.stepOutputs.join("、")}`)
  }
  if (summary.source) {
    parts.push(`来源：${mapExecutorLabel(summary.source)}`)
  }
  if (summary.checkpointResult) {
    parts.push(`确认结果：${summary.checkpointResult}`)
  }
  if (summary.hasSummary) {
    parts.push("包含摘要")
  }
  if (summary.hasRevisedDocument) {
    parts.push("包含修订稿")
  }
  if (summary.blockedByFailure) {
    parts.push("因前置失败被阻塞")
  }
  if (summary.errorType) {
    parts.push(`错误类型：${summary.errorType}`)
  }

  return parts.join("；") || formatCompactJson(summary)
}

function buildCard({ heading, status, title, body, footer = "", outputPreview = "" }) {
  return `
    <article class="workflow-card">
      <div class="attempt-head">
        <strong>${escapeHtml(heading)}</strong>
        <span>${escapeHtml(status)}</span>
      </div>
      <p class="attempt-text"><strong>${escapeHtml(title)}</strong></p>
      <p class="attempt-text">${escapeHtml(body)}</p>
      ${footer}
      ${outputPreview ? `<pre class="code-block small-code">${escapeHtml(outputPreview)}</pre>` : ""}
    </article>
  `
}

function buildLogMetaLine(label, value) {
  return `<p class="helper-text log-detail-line"><strong>${escapeHtml(label)}：</strong> ${escapeHtml(value)}</p>`
}

function buildLogFooter(log) {
  const chipItems = [
    `<span class="log-chip">${escapeHtml(mapLogKind(log.kind))}</span>`,
    `<span class="log-chip">${escapeHtml(mapExecutorLabel(log.executor))}</span>`,
  ]

  return `
    <div class="log-chip-row">${chipItems.join("")}</div>
    ${buildLogMetaLine("依赖步骤", formatList(log.dependsOn))}
    ${buildLogMetaLine("执行时间", `${formatDateTime(log.startedAt)} -> ${formatDateTime(log.finishedAt)}`)}
    ${buildLogMetaLine("耗时", formatDuration(log.durationMs))}
    ${buildLogMetaLine("输入摘要", formatLogInputSummary(log.inputSummary))}
    ${buildLogMetaLine("输出摘要", formatLogOutputSummary(log.outputSummary))}
  `
}

export function createResultsView({ dom, state, setError }) {
  const finalOutputPanel = createFinalOutputPanel({ dom, state, setError })
  const confirmationPanel = createConfirmationPanel({ dom, state })

  function setStatus(label, status) {
    dom.resultStatus.textContent = label || "-"
    dom.resultStatus.className = `result-status ${status || "idle"}`
  }

  function setHealthState({
    ok = false,
    model = "-",
    providerLabel = "模型 API",
    apiConfigured = false,
    agentEnabled = false,
    confirmationMode = "-",
    error = null,
  }) {
    dom.healthBadge.textContent = error ? "异常" : ok ? "就绪" : "离线"
    dom.healthBadge.className = `status-badge ${error ? "error" : ok ? "ok" : "pending"}`
    dom.healthModel.textContent = model || "-"
    dom.healthModelApi.textContent = error ? "不可用" : `${providerLabel || "模型 API"} / ${apiConfigured ? "已配置" : "缺少密钥"}`
    dom.healthAgent.textContent = error ? "不可用" : agentEnabled ? "Agent 编排" : "本地回退"
    const confirmationLabels = {
      manual_confirm: "人工确认",
      risk_based: "风险步骤确认",
    }
    dom.confirmationMode.textContent = error ? "不可用" : confirmationLabels[confirmationMode] || confirmationMode || "-"
  }

  function resetResultView() {
    setStatus("空闲", "idle")
    dom.executeButton.disabled = true
    setText(dom.intentionOutput, "等待规划结果。", { muted: true })
    setText(dom.missingOutput, "等待规划结果。", { muted: true })
    confirmationPanel.renderIdleState()
    setHtml(dom.planOutput, "<p class=\"muted\">等待规划结果。</p>")
    setHtml(dom.logsOutput, "<p class=\"muted\">执行后会在这里显示日志。</p>")
    finalOutputPanel.reset()
  }

  function renderSkillsCatalog(skills) {
    const safeSkills = skills || []
    setText(dom.skillCount, String(safeSkills.length))
    setText(dom.skillSummary, `${safeSkills.length} 个技能`)

    renderCards(dom.skillsOutput, safeSkills, "当前没有已注册的技能。", (skill) =>
      buildCard({
        heading: skill.title,
        status: "可用",
        title: skill.description,
        body: "当前已注册，可参与自动规划和执行。",
        footer: `<p class="helper-text">标识：${escapeHtml(skill.name)}</p>`,
      })
    )
  }

  function renderSkillsCatalogError(message) {
    setText(dom.skillCount, "-")
    setText(dom.skillSummary, "加载失败")
    setHtml(dom.skillsOutput, `<p class="muted">${escapeHtml(message)}</p>`)
  }

  function renderIntention(intention) {
    if (!intention) {
      setText(dom.intentionOutput, "任务理解仍在生成中，请稍候。", { muted: true })
      return
    }

    const lines = [
      `任务：${intention.primaryGoal || "-"}`,
      `意图类型：${mapIntentLabel(intention.intentType)}`,
      `识别到的意图：${mapIntentNames(intention.detectedIntentTypes || [intention.intentType])}`,
      `置信度：${typeof intention.confidence === "number" ? intention.confidence.toFixed(2) : "-"}`,
      `是否依赖文档：${intention.documentRequired ? "是" : "否"}`,
      `需要的文档：${mapDocumentKinds(intention.requiredDocumentKinds)}`,
      `推荐技能：${mapSkillNames(intention.recommendedSkills)}`,
      `未注册技能：${(intention.unsupportedPreferredSkills || []).join("、") || "-"}`,
      "",
      "说明：",
      ...((intention.notes || []).map((note) => `- ${note}`)),
    ]
    setText(dom.intentionOutput, lines.join("\n"))
  }

  function buildRenderableWorkflowResponse(data) {
    const fallback = state.data.latestPlanResponse || state.data.latestExecutionResponse || {}
    const safeData = data || {}
    return {
      ...fallback,
      ...safeData,
      intention: safeData.intention || fallback.intention || null,
      missingDocuments: safeData.missingDocuments || fallback.missingDocuments || null,
      plan: Array.isArray(safeData.plan) && safeData.plan.length
        ? safeData.plan
        : (Array.isArray(fallback.plan) ? fallback.plan : []),
    }
  }

  function renderMissingDocuments(missingDocuments) {
    if (!missingDocuments) {
      setText(dom.missingOutput, "没有缺件信息。")
      return
    }

    const required = mapDocumentKinds(missingDocuments.requiredKinds)
    const present = mapDocumentKinds(missingDocuments.presentKinds)
    const missing = mapDocumentKinds(missingDocuments.missingKinds) === "-"
      ? "无"
      : mapDocumentKinds(missingDocuments.missingKinds)
    const advice = Array.isArray(missingDocuments.advice) && missingDocuments.advice.length
      ? `<p><strong>建议：</strong> ${escapeHtml(missingDocuments.advice.join("；"))}</p>`
      : ""
    setHtml(dom.missingOutput, `
      <p><strong>就绪度：</strong> ${escapeHtml(READINESS_LABELS[missingDocuments.readiness] || missingDocuments.readiness || "-")}</p>
      <p><strong>需要：</strong> ${escapeHtml(required)}</p>
      <p><strong>已有：</strong> ${escapeHtml(present)}</p>
      <p><strong>缺少：</strong> ${escapeHtml(missing)}</p>
      ${advice}
    `)
  }

  function renderPlan(plan) {
    renderCards(dom.planOutput, plan, "没有可展示的计划。", (step) =>
      buildCard({
        heading: `步骤 ${step.stepNumber}`,
        status: STATUS_LABELS[step.status] || step.status,
        title: step.title,
        body: step.description,
        footer: [
          step.skill
            ? `<p class="helper-text">技能：${escapeHtml(mapSkillName(step.skill))}${step.requiresApproval ? " · 需要确认" : ""}</p>`
            : "",
          step.checkpoint
            ? `<p class="helper-text">检查点：${escapeHtml(mapConfirmationType((step.inputs || {}).confirmationType || step.checkpoint))}</p>`
            : "",
          Array.isArray(step.dependsOn) && step.dependsOn.length
            ? `<p class="helper-text">依赖步骤：${escapeHtml(step.dependsOn.join("、"))}</p>`
            : "",
          Array.isArray(step.outputs) && step.outputs.length
            ? `<p class="helper-text">输出：${escapeHtml(step.outputs.join("；"))}</p>`
            : "",
        ].filter(Boolean).join(""),
      })
    )
  }

  function renderLogs(logs) {
    renderCards(dom.logsOutput, logs, "当前还没有执行日志。", (log) =>
      buildCard({
        heading: `步骤 ${log.stepNumber}`,
        status: STATUS_LABELS[log.status] || log.status,
        title: log.title,
        body: log.message,
        footer: buildLogFooter(log),
        outputPreview: log.outputPreview || "",
      })
    )
  }

  function renderWorkflowResponse(data, { logs = [], finalOutput = null } = {}) {
    const renderData = buildRenderableWorkflowResponse(data)
    setStatus(STATUS_LABELS[renderData.status] || renderData.status || "-", renderData.status || "idle")
    renderIntention(renderData.intention)
    renderMissingDocuments(renderData.missingDocuments)
    renderPlan(renderData.plan)
    renderLogs(logs)
    finalOutputPanel.render(finalOutput)
    confirmationPanel.render(renderData, finalOutput)
  }

  function renderPlanResponse(data) {
    renderWorkflowResponse(data)
  }

  function renderExecuteResponse(data) {
    renderWorkflowResponse(data, {
      logs: data.logs,
      finalOutput: data.finalOutput,
    })
  }

  function renderJobResponse(data) {
    state.setLatestJobResponse(data)
    if (data && (data.finalOutput || (data.logs && data.logs.length))) {
      state.setLatestExecutionResponse(data)
    }
    renderExecuteResponse(data)
  }

  function bindInteractivePanels() {
    finalOutputPanel.bindEvents()
    confirmationPanel.bindEvents()
  }

  return {
    bindInteractivePanels,
    setStatus,
    setHealthState,
    resetResultView,
    renderSkillsCatalog,
    renderSkillsCatalogError,
    renderPlanResponse,
    renderExecuteResponse,
    renderJobResponse,
  }
}
