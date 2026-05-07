import { escapeHtml } from "../core/html.js"

function buildActionButtons(actions) {
  if (!Array.isArray(actions) || !actions.length) {
    return ""
  }

  return `
    <div class="chat-message-actions">
      ${actions.map((action) => `
        <button
          type="button"
          class="${escapeHtml(action.variant === "primary" ? "primary-button" : "ghost-button")} chat-inline-action"
          data-chat-action="${escapeHtml(action.action)}"
        >
          ${escapeHtml(action.label)}
        </button>
      `).join("")}
    </div>
  `
}

function renderChatBody(body) {
  const normalized = String(body || "").trim()
  if (!normalized) {
    return ""
  }

  const blocks = normalized.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean)
  return blocks
    .map((block) => {
      const lines = block.split("\n").map((line) => line.trim()).filter(Boolean)
      if (!lines.length) {
        return ""
      }

      const firstLine = lines[0]
      const remainingLines = lines.slice(1)
      const remainderUnordered = remainingLines.length && remainingLines.every((line) => /^[-*]\s+/.test(line))
      const remainderOrdered = remainingLines.length && remainingLines.every((line) => /^\d+\.\s+/.test(line))

      if (remainderUnordered || remainderOrdered) {
        const listTag = remainderOrdered ? "ol" : "ul"
        const listClass = remainderOrdered ? "chat-list ordered" : "chat-list"
        const itemPattern = remainderOrdered ? /^\d+\.\s+/ : /^[-*]\s+/
        return [
          `<p>${escapeHtml(firstLine)}</p>`,
          `<${listTag} class="${listClass}">${remainingLines
            .map((line) => `<li>${escapeHtml(line.replace(itemPattern, ""))}</li>`)
            .join("")}</${listTag}>`,
        ].join("")
      }

      const unordered = lines.every((line) => /^[-*]\s+/.test(line))
      if (unordered) {
        return `<ul class="chat-list">${lines
          .map((line) => `<li>${escapeHtml(line.replace(/^[-*]\s+/, ""))}</li>`)
          .join("")}</ul>`
      }

      const ordered = lines.every((line) => /^\d+\.\s+/.test(line))
      if (ordered) {
        return `<ol class="chat-list ordered">${lines
          .map((line) => `<li>${escapeHtml(line.replace(/^\d+\.\s+/, ""))}</li>`)
          .join("")}</ol>`
      }

      return `<p>${lines.map((line) => escapeHtml(line)).join("<br />")}</p>`
    })
    .join("")
}

export function createChat({ dom }) {
  let chatActionHandler = () => {}
  let chatSendHandler = () => {}

  function scrollToBottom() {
    dom.chatOutput.scrollTop = dom.chatOutput.scrollHeight
  }

  function appendMessage({ role, title = "", body = "", tone = "neutral", actions = [] }) {
    const article = document.createElement("article")
    article.className = `chat-message ${role} ${tone}`
    article.innerHTML = `
      <div class="chat-message-meta">
        <span>${escapeHtml(title || (role === "user" ? "你" : "Agent"))}</span>
      </div>
      <div class="chat-message-body">${renderChatBody(body)}</div>
      ${buildActionButtons(actions)}
    `
    dom.chatOutput.append(article)
    scrollToBottom()
  }

  function appendUserMessage(body) {
    appendMessage({
      role: "user",
      title: "你",
      body,
    })
  }

  function appendAssistantMessage({ title = "Agent", body, tone = "neutral", actions = [] }) {
    appendMessage({
      role: "assistant",
      title,
      body,
      tone,
      actions,
    })
  }

  function resetConversation() {
    dom.chatOutput.innerHTML = ""
    appendAssistantMessage({
      title: "ESG Agent",
      body: [
        "请直接告诉我你要处理什么 ESG 任务。",
        "你也可以先上传 ESG 报告草稿、碳排台账、治理说明等材料。",
        "我会先理解需求，再像 chatbot 一样把判断结果和执行结论直接回复给你。",
      ].join("\n\n"),
    })
  }

  function handleChatSend() {
    const message = dom.chatInput.value.trim()
    if (!message) {
      return
    }

    dom.chatInput.value = ""
    chatSendHandler(message)
  }

  function init({ onSendMessage, onAction } = {}) {
    chatSendHandler = typeof onSendMessage === "function" ? onSendMessage : () => {}
    chatActionHandler = typeof onAction === "function" ? onAction : () => {}

    dom.chatSendButton.addEventListener("click", handleChatSend)
    dom.chatInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.shiftKey) {
        return
      }
      event.preventDefault()
      handleChatSend()
    })

    dom.chatOutput.addEventListener("click", (event) => {
      const button = event.target.closest("[data-chat-action]")
      if (!button) {
        return
      }
      chatActionHandler(button.dataset.chatAction || "")
    })
  }

  return {
    init,
    appendUserMessage,
    appendAssistantMessage,
    resetConversation,
  }
}
