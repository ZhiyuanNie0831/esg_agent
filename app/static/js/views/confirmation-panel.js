import { mapConfirmationType, mapSkillNames } from "../config/labels.js"
import { escapeHtml, setHtml, setText } from "../core/html.js"

export function readTableMappingPreview(finalOutput) {
  const skillResults = (((finalOutput || {}).artifacts || {})["技能结果"] || {})
  const previewResult = skillResults.table_mapping_preview || {}
  const directCandidates = Array.isArray(previewResult.mappingCandidates) ? previewResult.mappingCandidates : []
  const nestedCandidates = Array.isArray(((previewResult.mappingPreview || {}).mappingCandidates))
    ? previewResult.mappingPreview.mappingCandidates
    : []
  const candidates = directCandidates.length ? directCandidates : nestedCandidates
  if (!candidates.length) {
    return null
  }

  return {
    summary: previewResult.summary || ((previewResult.mappingPreview || {}).summary) || "",
    mode: ((previewResult.mappingPreview || {}).mode) || previewResult.mode || "",
    targetSheet: ((previewResult.mappingPreview || {}).targetSheet) || "",
    crossCheck: previewResult.crossCheck || ((previewResult.mappingPreview || {}).crossCheck) || {},
    candidates,
  }
}

export function readApprovalStep(data) {
  const planSteps = Array.isArray((data || {}).plan) ? data.plan : []
  return planSteps.find((step) => step && step.checkpoint === "approval") || null
}

export function readApprovalContext(data) {
  const approvalStep = readApprovalStep(data)
  return approvalStep && approvalStep.inputs && typeof approvalStep.inputs === "object" ? approvalStep.inputs : {}
}

export function readConfirmationType(data, finalOutput = null) {
  if (readTableMappingPreview(finalOutput || (data || {}).finalOutput)) {
    return "table_mapping"
  }
  return String(readApprovalContext(data).confirmationType || "plan_review")
}

export function createConfirmationPanel({ dom, state }) {
  function clearPendingMappings() {
    state.setPendingTableMappings([])
    state.setPendingTableMappingsKey(null)
  }

  function renderIdleState() {
    setText(
      dom.confirmationOutput,
      "普通总结和审核会直接执行；当流程进入待确认状态后，这里会展示需要复核的计划、风险步骤或表格映射。",
      { muted: true }
    )
    clearPendingMappings()
  }

  function ensurePendingTableMappings(data, preview) {
    if (!preview || !Array.isArray(preview.candidates) || !preview.candidates.length) {
      clearPendingMappings()
      return
    }

    const mappingKey = [
      data && data.jobId ? data.jobId : "sync",
      ...(preview.candidates.map((item) => String(item.mappingId || ""))),
    ].join(":")
    if (state.data.pendingTableMappingsKey === mappingKey) {
      return
    }

    state.setPendingTableMappings(preview.candidates.map((item) => ({
      mappingId: item.mappingId || "",
      metric: item.metric || "",
      enabled: true,
      sheet: item.sheet || "",
      cell: item.cell || "",
      writePolicy: "only_empty",
      selectedCandidateIndex: 0,
      value: item.value,
      sourceDocument: item.sourceDocument || "",
      sourceSheet: item.sourceSheet || "",
      sourceColumn: item.sourceColumn || "",
      status: item.status || "",
      mode: item.mode || "",
      confidence: item.confidence || "",
      score: item.score,
      riskLevel: item.riskLevel || "",
      requiresConfirmation: Boolean(item.requiresConfirmation),
      reasons: Array.isArray(item.reasons) ? item.reasons.slice() : [],
      topCandidate: item.topCandidate && typeof item.topCandidate === "object" ? { ...item.topCandidate } : null,
      alternativeCandidates: Array.isArray(item.alternativeCandidates) ? item.alternativeCandidates.map((candidate) => ({ ...candidate })) : [],
      message: item.message || "",
      reviewRiskLevel: item.reviewRiskLevel || "",
      reviewApproved: item.reviewApproved,
      reviewIssue: item.reviewIssue || "",
      reviewSuggestedSheet: item.reviewSuggestedSheet || "",
      reviewSuggestedCell: item.reviewSuggestedCell || "",
    })))
    state.setPendingTableMappingsKey(mappingKey)
  }

  function buildConfirmActionButton() {
    return `
      <div class="confirmation-actions">
        <button
          type="button"
          class="primary-button"
          data-confirmation-action="confirm_execute"
        >
          确认并继续执行
        </button>
      </div>
    `
  }

  function buildGenericConfirmationSummary(data) {
    const safeData = data || {}
    const approvalContext = readApprovalContext(safeData)
    const confirmationType = readConfirmationType(safeData)
    const planSteps = Array.isArray(safeData.plan) ? safeData.plan : []
    const completedSteps = planSteps.filter((step) => step && step.status === "completed")
    const pendingSteps = planSteps.filter((step) => step && ["planned", "blocked"].includes(step.status))
    const executedSkills = mapSkillNames(safeData.executedSkills || [])
    const approvalRequiredSkills = Array.isArray(approvalContext.approvalRequiredSkills)
      ? approvalContext.approvalRequiredSkills.map((item) => item && item.title).filter(Boolean).join("、")
      : ""

    return `
      <div class="confirmation-panel">
        <div class="confirmation-review-grid">
          <article class="confirmation-review-card">
            <span>确认类型</span>
            <strong>${escapeHtml(mapConfirmationType(confirmationType))}</strong>
          </article>
          <article class="confirmation-review-card">
            <span>已完成</span>
            <strong>${escapeHtml(completedSteps.length ? `${completedSteps.length} 步` : "暂无")}</strong>
          </article>
          <article class="confirmation-review-card">
            <span>待继续</span>
            <strong>${escapeHtml(pendingSteps.length ? `${pendingSteps.length} 步` : "后续步骤")}</strong>
          </article>
        </div>
        <div class="confirmation-note">
          <p><strong>${escapeHtml(approvalContext.reason || "当前流程暂停在人工确认点。")}</strong></p>
          <p>${escapeHtml(approvalContext.guidance || "请检查任务理解、执行计划、日志和当前输出；确认无误后继续执行。")}</p>
        </div>
        ${buildConfirmActionButton()}
        <div class="confirmation-detail-grid">
          <p><strong>已完成步骤：</strong>${escapeHtml(completedSteps.length ? completedSteps.map((step) => step.title).join("、") : "暂无")}</p>
          <p><strong>待继续步骤：</strong>${escapeHtml(pendingSteps.length ? pendingSteps.map((step) => step.title).join("、") : "后续步骤将继续执行")}</p>
          <p><strong>已执行能力：</strong>${escapeHtml(executedSkills || "-")}</p>
          <p><strong>需要复核的能力：</strong>${escapeHtml(approvalRequiredSkills || "-")}</p>
        </div>
      </div>
    `
  }

  function buildMappingRows() {
    return state.readPendingTableMappings().map((item) => `
      <tr>
        <td><input type="checkbox" data-mapping-id="${escapeHtml(item.mappingId)}" data-mapping-field="enabled" ${item.enabled !== false ? "checked" : ""} /></td>
        <td>${escapeHtml(item.metric || "-")}</td>
        <td>${escapeHtml(item.sourceDocument || "-")}</td>
        <td>${escapeHtml([item.sourceSheet, item.sourceColumn].filter(Boolean).join(" / ") || "-")}</td>
        <td>${escapeHtml(item.value == null ? "-" : String(item.value))}</td>
        <td>
          <select class="mapping-select" data-mapping-id="${escapeHtml(item.mappingId)}" data-mapping-field="selectedCandidateIndex">
            ${state.readCandidateOptions(item).map((candidate, index) => `
              <option value="${index}" ${Number(item.selectedCandidateIndex || 0) === index ? "selected" : ""}>
                ${escapeHtml(candidate.cell ? `${candidate.sheet || "-"} / ${candidate.cell}` : "人工指定")}
              </option>
            `).join("")}
          </select>
        </td>
        <td><input class="mapping-input" type="text" data-mapping-id="${escapeHtml(item.mappingId)}" data-mapping-field="sheet" value="${escapeHtml(item.sheet || "")}" placeholder="工作表名" /></td>
        <td><input class="mapping-input" type="text" data-mapping-id="${escapeHtml(item.mappingId)}" data-mapping-field="cell" value="${escapeHtml(item.cell || "")}" placeholder="例如 B3" /></td>
        <td>
          <select class="mapping-select" data-mapping-id="${escapeHtml(item.mappingId)}" data-mapping-field="writePolicy">
            <option value="only_empty" ${item.writePolicy === "only_empty" ? "selected" : ""}>only_empty</option>
            <option value="allow_same" ${item.writePolicy === "allow_same" ? "selected" : ""}>allow_same</option>
            <option value="force_overwrite" ${item.writePolicy === "force_overwrite" ? "selected" : ""}>force_overwrite</option>
          </select>
        </td>
        <td>${escapeHtml(item.confidence || "-")} / ${escapeHtml(item.riskLevel || "-")}</td>
        <td>
          <p class="mapping-status">${escapeHtml(item.status || "-")}</p>
          <p class="mapping-message">${escapeHtml(item.message || "-")}</p>
          <p class="mapping-message">${escapeHtml(item.score == null ? "score=-" : `score=${item.score}`)}</p>
          <p class="mapping-message">${escapeHtml(item.requiresConfirmation ? "需要人工确认" : "可直接回填")}</p>
          ${item.reviewRiskLevel ? `<p class="mapping-message">${escapeHtml(`Review: ${item.reviewRiskLevel}${item.reviewApproved === false ? " / 未通过" : ""}`)}</p>` : ""}
          ${item.reviewIssue ? `<p class="mapping-message">${escapeHtml(item.reviewIssue)}</p>` : ""}
          ${item.reviewSuggestedCell ? `<p class="mapping-message">${escapeHtml(`建议位置：${item.reviewSuggestedSheet || item.sheet || "-"} / ${item.reviewSuggestedCell}`)}</p>` : ""}
          <p class="mapping-message">${escapeHtml(Array.isArray(item.reasons) && item.reasons.length ? item.reasons.join("；") : "-")}</p>
        </td>
      </tr>
    `).join("")
  }

  function renderMappingConfirmation(data, preview) {
    ensurePendingTableMappings(data, preview)
    const crossCheck = preview.crossCheck || {}
    const crossCheckNote = crossCheck.status
      ? `Review 交叉检查：${crossCheck.enabled ? crossCheck.status : "skipped"} / 风险 ${crossCheck.riskLevel || "unknown"}${crossCheck.blockWrite ? " / 已阻断写入" : ""}`
      : ""
    setHtml(dom.confirmationOutput, `
      <div class="confirmation-panel">
        <p class="helper-text">${escapeHtml(preview.summary || "请检查自动识别的填表位置，如有偏差可直接修改 sheet 或 cell。")}</p>
        ${crossCheckNote ? `<p class="helper-text">${escapeHtml(crossCheckNote)}</p>` : ""}
        <div class="confirmation-table-shell">
          <table class="confirmation-table">
            <thead>
              <tr>
                <th>写入</th>
                <th>指标</th>
                <th>来源文档</th>
                <th>来源位置</th>
                <th>结果值</th>
                <th>候选位置</th>
                <th>目标 Sheet</th>
                <th>目标 Cell</th>
                <th>写入策略</th>
                <th>置信度 / 风险</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>${buildMappingRows()}</tbody>
          </table>
        </div>
        <p class="helper-text">确认后会优先按你这里修改过的目标位置和写入策略回填；低置信度项需要保留这一行确认或显式关闭写入。</p>
        ${buildConfirmActionButton()}
      </div>
    `)
  }

  function render(data, finalOutput) {
    const preview = readTableMappingPreview(finalOutput)
    const awaitingConfirmation = data && data.status === "awaiting_confirmation"

    if (!awaitingConfirmation) {
      renderIdleState()
      return
    }

    if (!preview) {
      clearPendingMappings()
      setHtml(dom.confirmationOutput, buildGenericConfirmationSummary(data))
      return
    }

    renderMappingConfirmation(data, preview)
  }

  function normalizeMappingInput(input, field) {
    const rawValue = input.type === "checkbox" ? input.checked : input.value
    const normalized = state.normalizeMappingField(field, rawValue)
    if (input.type === "checkbox") {
      input.checked = Boolean(normalized)
    } else {
      input.value = normalized
    }
    return normalized
  }

  function handleMappingFieldEvent(event, { normalize = false } = {}) {
    const input = event.target.closest("[data-mapping-id][data-mapping-field]")
    if (!input) {
      return
    }

    const mappingId = input.dataset.mappingId
    const field = input.dataset.mappingField
    if (!mappingId || !field) {
      return
    }

    const value = normalize
      ? normalizeMappingInput(input, field)
      : (input.type === "checkbox" ? input.checked : input.value)
    state.updatePendingTableMapping(mappingId, field, value)
  }

  function bindEvents() {
    dom.confirmationOutput.addEventListener("input", (event) => {
      handleMappingFieldEvent(event)
    })
    dom.confirmationOutput.addEventListener("change", (event) => {
      handleMappingFieldEvent(event, { normalize: true })
    })
  }

  return {
    bindEvents,
    render,
    renderIdleState,
  }
}
