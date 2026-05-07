const SELECTORS = {
  form: "#workflow-form",
  chatOutput: "#chat-output",
  chatInput: "#chat-input",
  chatSendButton: "#chat-send-button",
  taskInput: "#task",
  uploadFilesInput: "#upload-files",
  uploadButton: "#upload-button",
  uploadStatus: "#upload-status",
  documentsInput: "#documents",
  documentsOutput: "#documents-output",
  documentCount: "#document-count",
  selectedSkillCount: "#selected-skill-count",
  selectedSkillsOutput: "#selected-skills-output",
  customSkillNameInput: "#custom-skill-name",
  addCustomSkillButton: "#add-custom-skill-button",
  skillPickerOutput: "#skill-picker-output",
  manualConfirmInput: "#manualConfirm",
  localFallbackInput: "#localFallbackEnabled",
  planButton: "#plan-button",
  executeButton: "#execute-button",
  clearConversationButton: "#clear-conversation-button",
  healthBadge: "#health-badge",
  healthModel: "#health-model",
  healthModelApi: "#health-model-api",
  healthAgent: "#health-agent",
  skillCount: "#skill-count",
  confirmationMode: "#confirmation-mode",
  resultStatus: "#result-status",
  errorBox: "#error-box",
  intentionOutput: "#intention-output",
  missingOutput: "#missing-output",
  confirmationOutput: "#confirmation-output",
  skillsOutput: "#skills-output",
  skillSummary: "#skill-summary",
  planOutput: "#plan-output",
  logsOutput: "#logs-output",
  summaryOutput: "#summary-output",
  esgWorkflowOutput: "#esg-workflow-output",
  evidenceOutput: "#evidence-output",
  downloadsOutput: "#downloads-output",
  revisedOutput: "#revised-output",
  artifactsOutput: "#artifacts-output",
}

export function createDom(root = document) {
  const dom = Object.fromEntries(
    Object.entries(SELECTORS).map(([key, selector]) => [key, root.querySelector(selector)])
  )
  const missing = Object.entries(dom)
    .filter(([, element]) => !element)
    .map(([key]) => `${key} (${SELECTORS[key]})`)

  if (missing.length) {
    throw new Error(`前端页面缺少必要节点：${missing.join("、")}`)
  }

  return dom
}
