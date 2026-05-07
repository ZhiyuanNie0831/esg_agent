import { escapeHtml, setHtml, setText } from "../core/html.js"

function decodeBase64ToBytes(base64Text) {
  const binary = atob(String(base64Text || ""))
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes
}

export function createFinalOutputPanel({ dom, state, setError }) {
  function renderEvidence(items) {
    if (!Array.isArray(items) || !items.length) {
      setHtml(dom.evidenceOutput, "<p class=\"muted\">执行完成后会在这里展示引用的材料位置。</p>", { muted: false })
      return
    }

    setHtml(
      dom.evidenceOutput,
      items.map((item) => `
        <article class="evidence-card">
          <p class="evidence-title"><strong>${escapeHtml(item.title || "证据")}</strong></p>
          <p class="evidence-meta">${escapeHtml(item.document || "未命名材料")} · ${escapeHtml(item.location || "-")}</p>
          ${item.sourceStep ? `<p class="evidence-meta">来源步骤：${escapeHtml(item.sourceStep)}</p>` : ""}
          <p class="evidence-excerpt">${escapeHtml(item.excerpt || "")}</p>
        </article>
      `).join(""),
      { muted: false }
    )
  }

  function renderDownloads(items) {
    if (!Array.isArray(items) || !items.length) {
      setHtml(dom.downloadsOutput, "<p class=\"muted\">执行完成后会在这里提供可下载文件。</p>", { muted: false })
      return
    }

    setHtml(
      dom.downloadsOutput,
      items.map((item, index) => `
        <article class="download-card">
          <p class="download-title"><strong>${escapeHtml(item.label || "下载文件")}</strong></p>
          <p class="download-meta">${escapeHtml(item.filename || "workflow_export.bin")}</p>
          <button
            type="button"
            class="secondary-button"
            data-download-index="${index}"
          >
            下载文件
          </button>
        </article>
      `).join(""),
      { muted: false }
    )
  }

  function renderEsgWorkflowOverview(finalOutput) {
    const skillResults = (((finalOutput || {}).artifacts || {})["技能结果"] || {})
    const standards = (((skillResults.esg_standard_selector || {}).standards) || [])
    const matrixStats = ((skillResults.esg_disclosure_matrix_builder || {}).matrixStats) || null
    const matrixItems = ((skillResults.esg_disclosure_matrix_builder || {}).disclosureMatrix) || []
    const dataRequests = ((skillResults.esg_data_request_builder || {}).dataRequests) || []
    const evidenceLinks = ((skillResults.esg_evidence_linker || {}).evidenceLinks) || []
    const reportResult = (skillResults.esg_report_writer || {})
    const hasReport = Boolean(reportResult.reportMarkdown || reportResult.revisedDocument)
    if (!standards.length && !matrixStats && !dataRequests.length && !evidenceLinks.length && !hasReport) {
      setHtml(dom.esgWorkflowOutput, "<p class=\"muted\">执行 ESG 报告流程后会在这里展示标准、披露矩阵、补资料清单和证据链接。</p>")
      return
    }

    const standardCards = standards.length
      ? standards.map((item) => `
          <span class="esg-chip">
            <strong>${escapeHtml(item.code || "-")}</strong>
            ${escapeHtml(item.name || "")}
          </span>
        `).join("")
      : `<span class="esg-chip"><strong>GRI</strong> 默认披露框架</span>`
    const statCards = matrixStats
      ? `
          <div class="esg-stat"><span>${escapeHtml(matrixStats.covered || 0)}</span><small>covered</small></div>
          <div class="esg-stat warn"><span>${escapeHtml(matrixStats.weak || 0)}</span><small>weak</small></div>
          <div class="esg-stat danger"><span>${escapeHtml(matrixStats.missing || 0)}</span><small>missing</small></div>
        `
      : ""
    const matrixRows = matrixItems.slice(0, 4).map((item) => `
      <tr>
        <td>${escapeHtml(item.topic || "-")}</td>
        <td><span class="esg-status ${escapeHtml(item.status || "unknown")}">${escapeHtml(item.status || "-")}</span></td>
        <td>${escapeHtml(Array.isArray(item.requiredData) && item.requiredData.length ? item.requiredData.slice(0, 2).join("；") : item.nextAction || "-")}</td>
      </tr>
    `).join("")
    const requestCards = dataRequests.slice(0, 3).map((item) => `
      <article class="esg-mini-card">
        <strong>${escapeHtml(item.topic || "待补资料")}</strong>
        <span>${escapeHtml(item.owner || "ESG 工作组")} · ${escapeHtml(item.priority || "-")}</span>
      </article>
    `).join("")
    const evidenceCards = evidenceLinks.slice(0, 3).map((item) => `
      <article class="esg-mini-card">
        <strong>${escapeHtml(item.claim || "证据链接")}</strong>
        <span>${escapeHtml(item.document || "-")} · ${escapeHtml(item.location || "-")}</span>
      </article>
    `).join("")

    setHtml(dom.esgWorkflowOutput, `
      <div class="esg-overview-grid">
        <section class="esg-overview-block">
          <h5>披露标准</h5>
          <div class="esg-chip-row">${standardCards}</div>
        </section>
        <section class="esg-overview-block">
          <h5>披露矩阵</h5>
          <div class="esg-stat-row">${statCards}</div>
          ${matrixRows ? `<table class="esg-matrix-mini"><tbody>${matrixRows}</tbody></table>` : `<p class="muted">暂无矩阵数据。</p>`}
        </section>
        <section class="esg-overview-block">
          <h5>补资料清单</h5>
          <div class="esg-card-stack">${requestCards || "<p class=\"muted\">暂无开放请求。</p>"}</div>
        </section>
        <section class="esg-overview-block">
          <h5>证据链接</h5>
          <div class="esg-card-stack">${evidenceCards || "<p class=\"muted\">暂无证据链接。</p>"}</div>
        </section>
        ${hasReport ? `
          <section class="esg-overview-block">
            <h5>报告草稿</h5>
            <div class="esg-card-stack">
              <article class="esg-mini-card">
                <strong>${escapeHtml(reportResult.wordCountRequirement?.description || `${reportResult.targetWordCount || "-"} 字`)}</strong>
                <span>估算字数 ${escapeHtml(reportResult.estimatedWordCount || "-")} · ${escapeHtml(reportResult.source || "local_skill")}</span>
              </article>
            </div>
          </section>
        ` : ""}
      </div>
    `)
  }

  function reset() {
    setText(dom.summaryOutput, "执行完成后会在这里输出总结。", { muted: true })
    renderEsgWorkflowOverview(null)
    renderEvidence([])
    renderDownloads([])
    setText(dom.revisedOutput, "如果某个技能产出了修订文稿，会显示在这里。", { muted: true })
    setText(dom.artifactsOutput, "执行完成后会在这里展示结构化产物。", { muted: true })
  }

  function render(finalOutput) {
    if (!finalOutput) {
      setText(dom.summaryOutput, "还没有最终输出。")
      renderEsgWorkflowOverview(null)
      renderEvidence([])
      renderDownloads([])
      setText(dom.revisedOutput, "还没有修订文稿。")
      setText(dom.artifactsOutput, "{}")
      return
    }

    const nextActions = Array.isArray(finalOutput.nextActions) && finalOutput.nextActions.length
      ? `\n\n下一步建议：\n- ${finalOutput.nextActions.join("\n- ")}`
      : ""
    setText(dom.summaryOutput, `${finalOutput.summaryText || "暂无总结。"}${nextActions}`)
    renderEsgWorkflowOverview(finalOutput)
    renderEvidence(finalOutput.evidence || [])
    renderDownloads(finalOutput.downloads || [])
    setText(dom.revisedOutput, finalOutput.revisedDocument || "本次流程没有产出修订文稿。")
    setText(dom.artifactsOutput, JSON.stringify(finalOutput.artifacts || {}, null, 2))
  }

  function downloadGeneratedFile(downloadIndex) {
    const downloads = (((state.data.latestExecutionResponse || {}).finalOutput || {}).downloads || [])
    const item = downloads[downloadIndex]
    if (item && item.downloadUrl) {
      const link = document.createElement("a")
      link.href = item.downloadUrl
      link.download = item.filename || "workflow_export.bin"
      document.body.append(link)
      link.click()
      link.remove()
      return
    }

    if (!item || !item.contentBase64) {
      setError("当前没有可下载的文件内容。")
      return
    }

    const blob = new Blob([decodeBase64ToBytes(item.contentBase64)], {
      type: item.mimeType || "application/octet-stream",
    })
    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = objectUrl
    link.download = item.filename || "workflow_export.bin"
    document.body.append(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(objectUrl)
  }

  function bindEvents() {
    dom.downloadsOutput.addEventListener("click", (event) => {
      const button = event.target.closest("[data-download-index]")
      if (!button) {
        return
      }

      const index = Number(button.dataset.downloadIndex)
      if (!Number.isInteger(index)) {
        return
      }

      downloadGeneratedFile(index)
    })
  }

  return {
    bindEvents,
    reset,
    render,
  }
}
