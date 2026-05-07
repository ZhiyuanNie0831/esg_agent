async function readJsonResponse(response, fallbackMessage) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : fallbackMessage
    throw new Error(detail)
  }
  return data
}

export function createWorkflowApi({ getSessionId }) {
  async function uploadDocuments(files) {
    const formData = new FormData()
    files.forEach((file) => {
      formData.append("files", file)
    })
    if (getSessionId()) {
      formData.append("sessionId", getSessionId())
    }

    const response = await fetch("/api/workflow/uploads", {
      method: "POST",
      body: formData,
    })
    return readJsonResponse(response, "文件上传失败。")
  }

  async function postJson(path, payload, fallbackMessage) {
    const response = await fetch(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    })
    return readJsonResponse(response, fallbackMessage)
  }

  return {
    async health() {
      const response = await fetch("/health")
      return readJsonResponse(response, `Health check failed with ${response.status}`)
    },

    async skillCatalog() {
      const response = await fetch("/api/workflow/skills")
      return readJsonResponse(response, `Skill catalog request failed with ${response.status}`)
    },

    uploadDocuments,

    plan(payload) {
      return postJson("/api/workflow/plan", payload, "规划请求失败。")
    },

    execute(payload) {
      return postJson("/api/workflow/execute", payload, "执行请求失败。")
    },

    createWorkflowJob(payload) {
      return postJson("/api/workflow/jobs", payload, "创建后台作业失败。")
    },

    async workflowJob(jobId) {
      const response = await fetch(`/api/workflow/jobs/${encodeURIComponent(jobId)}`)
      return readJsonResponse(response, "读取后台作业失败。")
    },

    approveWorkflowJob(jobId, planOverrides = null) {
      return postJson(
        `/api/workflow/jobs/${encodeURIComponent(jobId)}/approve`,
        {
          approved: true,
          planOverrides: planOverrides || {
            disabledStepIds: [],
            stepInputOverrides: {},
          },
        },
        "审批后台作业失败。"
      )
    },

    async createSession() {
      const response = await fetch("/api/workflow/sessions", { method: "POST" })
      return readJsonResponse(response, "创建 session 失败。")
    },

    async sessionState(sessionId) {
      const response = await fetch(`/api/workflow/sessions/${encodeURIComponent(sessionId)}`)
      return readJsonResponse(response, "读取 session 失败。")
    },

    async deleteSession(sessionId) {
      const response = await fetch(`/api/workflow/sessions/${encodeURIComponent(sessionId)}`, {
        method: "DELETE",
      })
      return readJsonResponse(response, "删除 session 失败。")
    },
  }
}
