import { escapeHtml } from "../core/html.js"

const PREVIEW_LIMIT = 160

function summarizeText(documentItem) {
  const rawText = (documentItem.ocrText || documentItem.contentText || "").trim()
  const compactText = rawText.replace(/\s+/g, " ")
  if (!compactText) {
    return "当前没有可显示的正文预览。"
  }

  if (compactText.length <= PREVIEW_LIMIT) {
    return compactText
  }

  return `${compactText.slice(0, PREVIEW_LIMIT - 1)}...`
}

function mergeDocuments(existingDocuments, incomingDocuments) {
  const merged = [...existingDocuments]

  incomingDocuments.forEach((incomingDocument) => {
    const index = merged.findIndex(
      (existingDocument) =>
        existingDocument.name === incomingDocument.name &&
        (existingDocument.source || "") === (incomingDocument.source || "")
    )

    if (index >= 0) {
      merged[index] = incomingDocument
      return
    }

    merged.push(incomingDocument)
  })

  return merged
}

function buildDocumentCard(documentItem) {
  const notes = Array.isArray(documentItem.notes) && documentItem.notes.length
    ? `<p class="helper-text">说明：${escapeHtml(documentItem.notes.join("；"))}</p>`
    : ""
  const parser = documentItem.parser ? ` · 解析器：${escapeHtml(documentItem.parser)}` : ""
  const meta = [
    `类型：${escapeHtml(documentItem.type || "other")}`,
    documentItem.sizeBytes ? `大小：${escapeHtml(String(documentItem.sizeBytes))} B` : "",
    parser,
  ]
    .filter(Boolean)
    .join(" ")

  return `
    <article class="workflow-card">
      <div class="attempt-head">
        <strong>${escapeHtml(documentItem.name || "未命名文档")}</strong>
        <span>${escapeHtml(documentItem.source || "manual")}</span>
      </div>
      <p class="attempt-text">${meta}</p>
      <p class="attempt-text">${escapeHtml(summarizeText(documentItem))}</p>
      ${notes}
    </article>
  `
}

export function createDocumentsPanel({
  dom,
  state,
  api,
  form,
  setError,
  clearError,
}) {
  function setUploadStatus(label) {
    dom.uploadStatus.textContent = label
  }

  function renderDocumentList() {
    let documents = []

    try {
      documents = form.readDocuments()
    } catch (error) {
      dom.documentCount.textContent = "-"
      dom.documentsOutput.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`
      return
    }

    dom.documentCount.textContent = `${documents.length} 个`
    if (!documents.length) {
      dom.documentsOutput.innerHTML = "<p class=\"muted\">还没有文档。</p>"
      return
    }

    dom.documentsOutput.innerHTML = documents.map(buildDocumentCard).join("")
  }

  function resetUploadState() {
    dom.uploadFilesInput.value = ""
    setUploadStatus("未上传文件")
    renderDocumentList()
  }

  async function handleUploadClick({ onUploaded, onError } = {}) {
    clearError()

    const files = Array.from(dom.uploadFilesInput.files || [])
    if (!files.length) {
      setError("请先选择要上传的文件。")
      return
    }

    let existingDocuments = []
    try {
      existingDocuments = form.readDocuments()
    } catch (error) {
      setError(`当前文档数据不可用，无法合并上传结果：${error.message}`)
      return
    }

    dom.uploadButton.disabled = true
    setUploadStatus(`正在读取 ${files.length} 个文件`)

    try {
      const data = await api.uploadDocuments(files)
      if (data.sessionId) {
        state.setSessionId(data.sessionId)
      }
      const mergedDocuments = Array.isArray(data.mergedDocuments) && data.mergedDocuments.length
        ? data.mergedDocuments
        : mergeDocuments(existingDocuments, data.documents || [])
      form.setDocuments(mergedDocuments)
      state.resetLatestPayload()
      renderDocumentList()

      const warningCount = Array.isArray(data.warnings) ? data.warnings.length : 0
      setUploadStatus(warningCount ? `已读取 ${data.total} 个文件，包含 ${warningCount} 条提示` : `已读取 ${data.total} 个文件`)
      dom.uploadFilesInput.value = ""

      if (typeof onUploaded === "function") {
        await onUploaded({
          total: data.total,
          documents: data.documents || [],
          mergedDocuments,
          warnings: data.warnings || [],
        })
      }
    } catch (error) {
      setUploadStatus("上传失败")
      setError(error.message)
      if (typeof onError === "function") {
        onError(error)
      }
    } finally {
      dom.uploadButton.disabled = false
    }
  }

  return {
    renderDocumentList,
    resetUploadState,
    handleUploadClick,
  }
}
