const SESSION_STORAGE_KEY = "workflow-session-id-v2"
const JOB_STORAGE_KEY = "workflow-job-id-v2"

function readStorage(key) {
  try {
    return window.localStorage.getItem(key) || ""
  } catch (error) {
    return ""
  }
}

function writeStorage(key, value) {
  try {
    if (!value) {
      window.localStorage.removeItem(key)
      return
    }
    window.localStorage.setItem(key, String(value))
  } catch (error) {
    // Browser storage is optional for the workflow surface.
  }
}

function normalizeSkillNames(skillNames) {
  return (skillNames || []).reduce((result, skillName) => {
    const normalized = String(skillName || "").trim()
    if (normalized && !result.includes(normalized)) {
      result.push(normalized)
    }
    return result
  }, [])
}

function normalizeMappingField(field, value) {
  if (field === "enabled" || field === "requiresConfirmation") {
    return Boolean(value)
  }
  if (field === "selectedCandidateIndex") {
    const parsed = Number.parseInt(String(value || "0"), 10)
    return Number.isInteger(parsed) && parsed >= 0 ? parsed : 0
  }
  if (field === "writePolicy") {
    const normalizedPolicy = String(value || "").trim()
    return ["only_empty", "allow_same", "force_overwrite"].includes(normalizedPolicy)
      ? normalizedPolicy
      : "only_empty"
  }

  const normalized = String(value || "")
  if (field === "cell") {
    return normalized.trim().replace(/\s+/g, "").toUpperCase()
  }
  if (field === "sheet") {
    return normalized.trim()
  }
  return normalized
}

function readCandidateOptions(item) {
  const topCandidate = item && item.topCandidate && typeof item.topCandidate === "object"
    ? [{ ...item.topCandidate }]
    : []
  const alternatives = Array.isArray(item && item.alternativeCandidates)
    ? item.alternativeCandidates
      .filter((candidate) => candidate && typeof candidate === "object")
      .map((candidate) => ({ ...candidate }))
    : []
  const options = [...topCandidate, ...alternatives]
  if (options.length) {
    return options
  }

  return [{
    sheet: item && item.sheet ? item.sheet : "",
    cell: item && item.cell ? item.cell : "",
    status: item && item.status ? item.status : "",
    confidence: item && item.confidence ? item.confidence : "",
    score: item && item.score != null ? item.score : null,
    riskLevel: item && item.riskLevel ? item.riskLevel : "",
    requiresConfirmation: Boolean(item && item.requiresConfirmation),
    reasons: Array.isArray(item && item.reasons) ? item.reasons.slice() : [],
    message: item && item.message ? item.message : "",
  }]
}

function resolveCandidateOption(item, index = 0) {
  const options = readCandidateOptions(item)
  const normalizedIndex = Math.max(0, Math.min(Number(index) || 0, Math.max(0, options.length - 1)))
  return options[normalizedIndex] || {}
}

export function createWorkflowState() {
  const data = {
    sessionId: null,
    latestPayload: null,
    latestPlanResponse: null,
    latestExecutionResponse: null,
    latestJobResponse: null,
    latestJobId: null,
    pendingTableMappings: [],
    pendingTableMappingsKey: null,
    availableSkills: [],
    selectedSkills: [],
  }

  function readSessionId() {
    return data.sessionId || ""
  }

  function setSessionId(sessionId) {
    data.sessionId = String(sessionId || "").trim() || null
    writeStorage(SESSION_STORAGE_KEY, data.sessionId)
    return data.sessionId
  }

  function readJobId() {
    return data.latestJobId || ""
  }

  function setJobId(jobId) {
    data.latestJobId = String(jobId || "").trim() || null
    writeStorage(JOB_STORAGE_KEY, data.latestJobId)
    return data.latestJobId
  }

  function setLatestJobResponse(response) {
    data.latestJobResponse = response
    if (response && response.jobId) {
      setJobId(response.jobId)
    }
  }

  function resetLatestJobResponse() {
    data.latestJobResponse = null
    setJobId(null)
  }

  function setPendingTableMappings(mappings) {
    data.pendingTableMappings = Array.isArray(mappings)
      ? mappings.map((item) => ({ ...item }))
      : []
    return data.pendingTableMappings
  }

  function readPendingTableMappings() {
    return Array.isArray(data.pendingTableMappings)
      ? data.pendingTableMappings.map((item) => ({ ...item }))
      : []
  }

  function updatePendingTableMapping(mappingId, field, value) {
    if (!mappingId || !field) {
      return
    }

    setPendingTableMappings(
      readPendingTableMappings().map((item) => {
        if (item.mappingId !== mappingId) {
          return item
        }

        const normalizedValue = normalizeMappingField(field, value)
        if (field === "selectedCandidateIndex") {
          const selectedOption = resolveCandidateOption(item, normalizedValue)
          return {
            ...item,
            selectedCandidateIndex: normalizedValue,
            sheet: normalizeMappingField("sheet", selectedOption.sheet || item.sheet),
            cell: normalizeMappingField("cell", selectedOption.cell || item.cell),
            status: selectedOption.status || item.status || "",
            confidence: selectedOption.confidence || item.confidence || "",
            score: selectedOption.score != null ? selectedOption.score : item.score,
            riskLevel: selectedOption.riskLevel || item.riskLevel || "",
            requiresConfirmation: Boolean(selectedOption.requiresConfirmation),
            reasons: Array.isArray(selectedOption.reasons)
              ? selectedOption.reasons.slice()
              : (Array.isArray(item.reasons) ? item.reasons.slice() : []),
            message: selectedOption.message || item.message || "",
            reviewRiskLevel: item.reviewRiskLevel || "",
            reviewApproved: item.reviewApproved,
            reviewIssue: item.reviewIssue || "",
            reviewSuggestedSheet: item.reviewSuggestedSheet || "",
            reviewSuggestedCell: item.reviewSuggestedCell || "",
          }
        }

        return { ...item, [field]: normalizedValue }
      })
    )
  }

  function readActivePlan() {
    if (data.latestJobResponse && Array.isArray(data.latestJobResponse.plan) && data.latestJobResponse.plan.length) {
      return data.latestJobResponse.plan
    }
    if (data.latestExecutionResponse && Array.isArray(data.latestExecutionResponse.plan) && data.latestExecutionResponse.plan.length) {
      return data.latestExecutionResponse.plan
    }
    if (data.latestPlanResponse && Array.isArray(data.latestPlanResponse.plan) && data.latestPlanResponse.plan.length) {
      return data.latestPlanResponse.plan
    }
    return []
  }

  function buildWorkflowJobPlanOverrides() {
    const tableFillerStep = readActivePlan().find((step) => step && step.skill === "table_filler")
    const manualMappings = readPendingTableMappings()
      .filter((item) => item && item.mappingId)
      .map((item) => ({
        mappingId: item.mappingId,
        enabled: item.enabled !== false,
        metric: item.metric || "",
        sheet: normalizeMappingField("sheet", item.sheet),
        cell: normalizeMappingField("cell", item.cell),
        writePolicy: normalizeMappingField("writePolicy", item.writePolicy),
        selectedCandidateIndex: normalizeMappingField("selectedCandidateIndex", item.selectedCandidateIndex),
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
        topCandidate: item.topCandidate || null,
        alternativeCandidates: Array.isArray(item.alternativeCandidates) ? item.alternativeCandidates.slice() : [],
        message: item.message || "",
        reviewRiskLevel: item.reviewRiskLevel || "",
        reviewApproved: item.reviewApproved,
        reviewIssue: item.reviewIssue || "",
        reviewSuggestedSheet: item.reviewSuggestedSheet || "",
        reviewSuggestedCell: item.reviewSuggestedCell || "",
      }))

    if (!tableFillerStep || !tableFillerStep.stepId || !manualMappings.length) {
      return {
        disabledStepIds: [],
        stepInputOverrides: {},
      }
    }

    return {
      disabledStepIds: [],
      stepInputOverrides: {
        [tableFillerStep.stepId]: {
          requireConfirmedCandidates: true,
          manualMappings,
        },
      },
    }
  }

  function setLatestPayload(payload) {
    data.latestPayload = payload
  }

  function resetRunState() {
    data.latestPayload = null
    data.latestPlanResponse = null
    data.latestExecutionResponse = null
    resetLatestJobResponse()
    setPendingTableMappings([])
    data.pendingTableMappingsKey = null
  }

  function setAvailableSkills(skills) {
    data.availableSkills = Array.isArray(skills) ? [...skills] : []
  }

  function setSelectedSkills(skillNames) {
    data.selectedSkills = normalizeSkillNames(skillNames)
    return readSelectedSkills()
  }

  function addSelectedSkill(skillName) {
    const normalized = normalizeSkillNames([skillName])[0]
    if (!normalized || data.selectedSkills.includes(normalized)) {
      return false
    }
    data.selectedSkills = [...data.selectedSkills, normalized]
    return true
  }

  function removeSelectedSkill(skillName) {
    const normalized = String(skillName || "").trim()
    if (!normalized || !data.selectedSkills.includes(normalized)) {
      return false
    }
    data.selectedSkills = data.selectedSkills.filter((item) => item !== normalized)
    return true
  }

  function readSelectedSkills() {
    return [...data.selectedSkills]
  }

  function findSkillDescriptor(skillName) {
    return data.availableSkills.find((skill) => skill.name === skillName) || null
  }

  return {
    data,
    readStoredSessionId: () => readStorage(SESSION_STORAGE_KEY),
    readStoredJobId: () => readStorage(JOB_STORAGE_KEY),
    readSessionId,
    setSessionId,
    readJobId,
    setJobId,
    setLatestPayload,
    resetLatestPayload: () => { data.latestPayload = null },
    setLatestPlanResponse: (response) => { data.latestPlanResponse = response },
    resetLatestPlanResponse: () => { data.latestPlanResponse = null },
    setLatestExecutionResponse: (response) => { data.latestExecutionResponse = response },
    resetLatestExecutionResponse: () => { data.latestExecutionResponse = null },
    setLatestJobResponse,
    resetLatestJobResponse,
    resetRunState,
    hasLatestExecutionResponse: () => Boolean(data.latestExecutionResponse),
    setAvailableSkills,
    setSelectedSkills,
    addSelectedSkill,
    removeSelectedSkill,
    readSelectedSkills,
    findSkillDescriptor,
    setPendingTableMappings,
    readPendingTableMappings,
    updatePendingTableMapping,
    setPendingTableMappingsKey: (key) => {
      data.pendingTableMappingsKey = String(key || "").trim() || null
      return data.pendingTableMappingsKey
    },
    normalizeMappingField,
    readCandidateOptions,
    buildWorkflowJobPlanOverrides,
  }
}
