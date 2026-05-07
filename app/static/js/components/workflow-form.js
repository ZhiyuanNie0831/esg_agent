import { parseJsonArray } from "../core/html.js"

export function createWorkflowForm({ dom, state, skillSetEditor }) {
  function setDocuments(documents) {
    dom.documentsInput.value = JSON.stringify(documents || [], null, 2)
  }

  function readDocuments() {
    try {
      return parseJsonArray(dom.documentsInput.value, "documents")
    } catch (error) {
      throw new Error(`documents JSON 解析失败: ${error.message}`)
    }
  }

  function setTask(task) {
    dom.taskInput.value = String(task || "").trim()
  }

  function readTask() {
    return dom.taskInput.value.trim()
  }

  function readPayload() {
    const task = readTask()
    if (!task) {
      throw new Error("请先填写任务描述。")
    }

    return {
      sessionId: state.readSessionId() || null,
      task,
      documents: readDocuments(),
      manualConfirm: dom.manualConfirmInput.checked,
      agentMode: "on",
      localFallbackEnabled: dom.localFallbackInput ? dom.localFallbackInput.checked : true,
      preferredSkills: skillSetEditor.readSelection(),
      context: {},
    }
  }

  function clearForm() {
    dom.form.reset()
    setDocuments([])
    skillSetEditor.setSelection([], { notify: false })
  }

  function buildPayloadFromSession(session) {
    if (!session || !session.task) {
      return null
    }

    return {
      sessionId: session.sessionId || state.readSessionId() || null,
      task: String(session.task || "").trim(),
      documents: Array.isArray(session.documents) ? session.documents : [],
      manualConfirm: Boolean(session.manualConfirm),
      agentMode: "on",
      localFallbackEnabled: session.localFallbackEnabled !== false,
      preferredSkills: Array.isArray(session.preferredSkills) ? session.preferredSkills : [],
      context: session.context || {},
    }
  }

  function fillFromPayload(payload) {
    setTask(payload.task || "")
    setDocuments(Array.isArray(payload.documents) ? payload.documents : [])
    skillSetEditor.setSelection(payload.preferredSkills || [], { notify: false })
    dom.manualConfirmInput.checked = Boolean(payload.manualConfirm)
    if (dom.localFallbackInput) {
      dom.localFallbackInput.checked = payload.localFallbackEnabled !== false
    }
  }

  function mergeTaskMessage(message, { replace = false } = {}) {
    const normalized = String(message || "").trim()
    if (!normalized) {
      return readTask()
    }

    if (replace || !readTask()) {
      setTask(normalized)
      return normalized
    }

    const merged = `${readTask()}\n补充说明：${normalized}`
    setTask(merged)
    return merged
  }

  return {
    setDocuments,
    readDocuments,
    setTask,
    readTask,
    readPayload,
    clearForm,
    buildPayloadFromSession,
    fillFromPayload,
    mergeTaskMessage,
  }
}
