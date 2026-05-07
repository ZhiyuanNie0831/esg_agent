import { createWorkflowApi } from "./api/workflow-api.js?v=20260507-confirm-button"
import { createChat } from "./components/chat.js?v=20260507-confirm-button"
import { createDocumentsPanel } from "./components/documents-panel.js?v=20260507-confirm-button"
import { createSkillSetEditor } from "./components/skill-set.js?v=20260507-confirm-button"
import { createWorkflowForm } from "./components/workflow-form.js?v=20260507-confirm-button"
import { createDom } from "./core/dom.js?v=20260507-confirm-button"
import { setText } from "./core/html.js?v=20260507-confirm-button"
import { createWorkflowState } from "./core/workflow-state.js?v=20260507-confirm-button"
import { createChatMessageFactory } from "./views/chat-messages.js?v=20260507-confirm-button"
import { createResultsView } from "./views/results-view.js?v=20260507-confirm-button"

const CONFIRM_COMMANDS = new Set(["确认执行", "确认", "执行", "开始执行", "继续执行", "ok", "yes"])
const CLEAR_COMMANDS = new Set(["清空", "重置", "重新开始", "reset", "restart"])

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function normalizeMessage(message) {
  return String(message || "").trim()
}

function normalizeCommand(message) {
  return normalizeMessage(message).toLowerCase()
}

function isConfirmCommand(message) {
  return CONFIRM_COMMANDS.has(normalizeCommand(message))
}

function isClearCommand(message) {
  return CLEAR_COMMANDS.has(normalizeCommand(message))
}

function shouldReplaceTask({ currentTask, hasExecuted }) {
  return !normalizeMessage(currentTask) || hasExecuted
}

export function createWorkflowApp() {
  const dom = createDom()
  const state = createWorkflowState()
  const api = createWorkflowApi({
    getSessionId: () => state.readSessionId(),
  })

  function setError(message) {
    setText(dom.errorBox, message)
    dom.errorBox.classList.remove("hidden")
  }

  function clearError() {
    setText(dom.errorBox, "")
    dom.errorBox.classList.add("hidden")
  }

  const results = createResultsView({ dom, state, setError })
  const chat = createChat({ dom })
  const skillSetEditor = createSkillSetEditor({
    dom,
    state,
    onChange: handleDraftChange,
  })
  const form = createWorkflowForm({ dom, state, skillSetEditor })
  const documentsPanel = createDocumentsPanel({
    dom,
    state,
    api,
    form,
    setError,
    clearError,
  })
  const messages = createChatMessageFactory({ state, form })

  async function waitForWorkflowJob(jobId, { announceInChat = true } = {}) {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const data = await api.workflowJob(jobId)
      results.renderJobResponse(data)

      if (data.status === "queued" || data.status === "running") {
        await wait(1000)
        continue
      }

      if (announceInChat) {
        if (data.status === "awaiting_confirmation") {
          chat.appendAssistantMessage(messages.buildAwaitingConfirmationChatMessage(data))
        } else {
          chat.appendAssistantMessage(messages.buildExecuteChatMessage(data))
        }
      }
      return data
    }

    throw new Error("后台作业等待超时，请稍后刷新查看。")
  }

  async function ensureSession() {
    const storedSessionId = state.readStoredSessionId()
    if (storedSessionId) {
      state.setSessionId(storedSessionId)
      try {
        const session = await api.sessionState(storedSessionId)
        hydrateSessionState(session)
        const latestJobId = session.latestJobId || state.readStoredJobId()
        if (latestJobId && !session.latestExecutionResponse) {
          try {
            const job = await api.workflowJob(latestJobId)
            results.renderJobResponse(job)
          } catch (error) {
            state.setJobId(null)
          }
        }
        return session
      } catch (error) {
        state.setSessionId(null)
      }
    }

    const session = await api.createSession()
    hydrateSessionState(session)
    return session
  }

  async function resetSession() {
    const currentSessionId = state.readSessionId()
    if (currentSessionId) {
      try {
        await api.deleteSession(currentSessionId)
      } catch (error) {
        // A stale session should not block starting a new workspace.
      }
    }

    state.setSessionId(null)
    const session = await api.createSession()
    hydrateSessionState(session)
    return session
  }

  function hydrateSessionState(session) {
    if (!session || typeof session !== "object") {
      state.resetRunState()
      results.resetResultView()
      return
    }

    state.setSessionId(session.sessionId || state.readSessionId() || null)
    form.fillFromPayload({
      task: session.task || "",
      documents: Array.isArray(session.documents) ? session.documents : [],
      preferredSkills: session.preferredSkills || [],
      manualConfirm: Boolean(session.manualConfirm),
      agentMode: "on",
      localFallbackEnabled: session.localFallbackEnabled !== false,
    })
    documentsPanel.renderDocumentList()

    const latestPayload = form.buildPayloadFromSession(session)
    if (latestPayload) {
      state.setLatestPayload(latestPayload)
    } else {
      state.resetLatestPayload()
    }

    if (session.latestPlanResponse) {
      state.setLatestPlanResponse(session.latestPlanResponse)
    } else {
      state.resetLatestPlanResponse()
    }
    state.setJobId(session.latestJobId || state.readStoredJobId() || null)

    if (session.latestExecutionResponse) {
      state.setLatestExecutionResponse(session.latestExecutionResponse)
      results.renderExecuteResponse(session.latestExecutionResponse)
      return
    }
    state.resetLatestExecutionResponse()

    if (session.latestPlanResponse) {
      results.renderPlanResponse(session.latestPlanResponse)
      return
    }

    results.resetResultView()
  }

  function readPayloadOrShowError() {
    try {
      return form.readPayload()
    } catch (error) {
      setError(error.message)
      return null
    }
  }

  function setButtons({ planning, canExecute }) {
    dom.planButton.disabled = planning
    dom.chatSendButton.disabled = planning
    dom.executeButton.disabled = !canExecute
  }

  function resetDraftState() {
    state.resetRunState()
    results.resetResultView()
    clearError()
  }

  function clearWorkspace() {
    form.clearForm()
    resetDraftState()
    documentsPanel.resetUploadState()
    chat.resetConversation()
  }

  async function loadHealthStatus() {
    try {
      const data = await api.health()
      results.setHealthState(data)
    } catch (error) {
      results.setHealthState({ error })
    }
  }

  async function loadSkillCatalog() {
    try {
      const data = await api.skillCatalog()
      skillSetEditor.setCatalog(data.skills || [])
      results.renderSkillsCatalog(data.skills || [])
    } catch (error) {
      skillSetEditor.setCatalogError(error.message)
      results.renderSkillsCatalogError(error.message)
    }
  }

  async function planWithPayload(payload, { announceInChat = true } = {}) {
    clearError()
    state.setLatestPayload(payload)
    setButtons({ planning: true, canExecute: false })
    results.setStatus("规划中", "planned")

    try {
      const data = await api.plan(payload)
      if (data.sessionId) {
        state.setSessionId(data.sessionId)
      }
      state.setLatestPlanResponse(data)
      results.renderPlanResponse(data)
      if (announceInChat) {
        chat.appendAssistantMessage(messages.buildPlanChatMessage(data))
      }
      setButtons({ planning: false, canExecute: data.status === "ready_to_execute" })
      return data
    } catch (error) {
      results.setStatus("失败", "failed")
      setError(error.message)
      if (announceInChat) {
        chat.appendAssistantMessage(messages.buildPlanningErrorMessage(error))
      }
      return null
    } finally {
      dom.planButton.disabled = false
      dom.chatSendButton.disabled = false
    }
  }

  async function planCurrentPayload({ announceInChat = true, blockedMessageBuilder = null } = {}) {
    const payload = readPayloadOrShowError()
    if (!payload) {
      if (typeof blockedMessageBuilder === "function") {
        chat.appendAssistantMessage(blockedMessageBuilder())
      }
      return { response: null, blocked: true }
    }

    return {
      response: await planWithPayload(payload, { announceInChat }),
      blocked: false,
    }
  }

  async function executeCurrentPayload({ announceInChat = true } = {}) {
    clearError()

    const payload = state.data.latestPayload || readPayloadOrShowError()
    if (!payload) {
      return null
    }

    setButtons({ planning: false, canExecute: false })
    results.setStatus("执行中", "running")

    try {
      const job = await api.createWorkflowJob({
        ...payload,
        approved: false,
        planOverrides: {
          disabledStepIds: [],
          stepInputOverrides: {},
        },
      })
      if (job.sessionId) {
        state.setSessionId(job.sessionId)
      }
      results.renderJobResponse(job)
      return await waitForWorkflowJob(job.jobId, { announceInChat })
    } catch (error) {
      results.setStatus("失败", "failed")
      setError(error.message)
      if (announceInChat) {
        chat.appendAssistantMessage(messages.buildExecutionErrorMessage(error))
      }
      return null
    } finally {
      dom.executeButton.disabled = false
    }
  }

  async function confirmCurrentPlan({ announceUserMessage = false } = {}) {
    if (state.data.latestJobResponse && state.data.latestJobResponse.status === "awaiting_confirmation") {
      if (announceUserMessage) {
        chat.appendUserMessage("确认执行")
      }
      try {
        const job = await api.approveWorkflowJob(
          state.data.latestJobResponse.jobId,
          state.buildWorkflowJobPlanOverrides()
        )
        results.renderJobResponse(job)
        return await waitForWorkflowJob(job.jobId)
      } catch (error) {
        setError(error.message)
        chat.appendAssistantMessage(messages.buildExecutionErrorMessage(error))
        return null
      }
    }

    if (dom.executeButton.disabled) {
      chat.appendAssistantMessage(messages.buildNoExecutablePlanMessage())
      return null
    }

    if (announceUserMessage) {
      chat.appendUserMessage("确认执行")
    }

    return executeCurrentPayload()
  }

  async function handlePlanSubmit(event) {
    event.preventDefault()
    await planCurrentPayload({ blockedMessageBuilder: messages.buildPlanBlockedMessage })
  }

  async function handleConversationMessage(message) {
    chat.appendUserMessage(message)

    if (isClearCommand(message)) {
      await handleClearClick()
      chat.appendAssistantMessage(messages.buildConversationClearedMessage())
      return
    }

    if (isConfirmCommand(message)) {
      await confirmCurrentPlan()
      return
    }

    form.mergeTaskMessage(message, {
      replace: shouldReplaceTask({
        currentTask: form.readTask(),
        hasExecuted: state.hasLatestExecutionResponse(),
      }),
    })
    resetDraftState()

    const { blocked } = await planCurrentPayload()
    if (blocked) {
      chat.appendAssistantMessage(messages.buildTaskContextErrorMessage())
    }
  }

  async function handleUploadSuccess({ total, documents, mergedDocuments, warnings }) {
    const uploadedDocuments = Array.isArray(documents) && documents.length ? documents : mergedDocuments.slice(-total)
    const names = uploadedDocuments.map((documentItem) => documentItem.name).join("、")
    chat.appendAssistantMessage(
      messages.buildUploadMergedMessage({
        total,
        names,
        warnings,
      })
    )

    if (!form.readTask()) {
      chat.appendAssistantMessage(messages.buildUploadAwaitingTaskMessage())
      return
    }

    chat.appendAssistantMessage(messages.buildUploadReplanMessage())
    resetDraftState()
    await planCurrentPayload()
  }

  async function handleClearClick() {
    clearWorkspace()
    try {
      await resetSession()
    } catch (error) {
      setError(error.message)
    }
  }

  function handleDraftChange() {
    resetDraftState()
  }

  async function handleChatAction(action) {
    if (action === "confirm_execute") {
      await confirmCurrentPlan({ announceUserMessage: true })
      return
    }

    if (action === "clear_conversation") {
      await handleClearClick()
      return
    }

    if (action === "plan_current") {
      await planCurrentPayload()
    }
  }

  async function handleConfirmationPanelClick(event) {
    const button = event.target.closest("[data-confirmation-action]")
    if (!button || !dom.confirmationOutput.contains(button)) {
      return
    }

    event.preventDefault()
    button.disabled = true
    try {
      await handleChatAction(button.dataset.confirmationAction || "")
    } finally {
      if (button.isConnected) {
        button.disabled = false
      }
    }
  }

  function bindEvents() {
    skillSetEditor.init()
    chat.init({
      onSendMessage: handleConversationMessage,
      onAction: handleChatAction,
    })
    results.bindInteractivePanels()

    dom.form.addEventListener("submit", handlePlanSubmit)
    dom.executeButton.addEventListener("click", () => executeCurrentPayload())
    dom.uploadButton.addEventListener("click", () => documentsPanel.handleUploadClick({ onUploaded: handleUploadSuccess }))
    dom.clearConversationButton.addEventListener("click", handleClearClick)
    dom.confirmationOutput.addEventListener("click", handleConfirmationPanelClick)
    dom.taskInput.addEventListener("input", handleDraftChange)
    dom.manualConfirmInput.addEventListener("change", handleDraftChange)
    dom.localFallbackInput.addEventListener("change", handleDraftChange)
    dom.documentsInput.addEventListener("input", () => {
      handleDraftChange()
      documentsPanel.renderDocumentList()
    })
  }

  function initializeView() {
    clearWorkspace()
  }

  async function init() {
    bindEvents()
    initializeView()
    try {
      await ensureSession()
    } catch (error) {
      setError(error.message)
    }
    await Promise.all([loadHealthStatus(), loadSkillCatalog()])
  }

  return {
    init,
  }
}
