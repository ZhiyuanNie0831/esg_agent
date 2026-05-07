export const STATUS_LABELS = {
  idle: "空闲",
  queued: "排队中",
  running: "执行中",
  planned: "已规划",
  ready_to_execute: "可执行",
  awaiting_confirmation: "等待确认",
  completed: "已完成",
  needs_documents: "缺少材料",
  blocked: "已阻塞",
  failed: "失败",
}

export const READINESS_LABELS = {
  ready: "就绪",
  partial: "部分就绪",
  missing: "缺失",
}

export const INTENT_LABELS = {
  review: "审核",
  count: "统计",
  summarize: "总结",
  revise: "修订",
  check_missing: "缺件检查",
  general: "通用处理",
}

export const DOCUMENT_KIND_LABELS = {
  invoice: "发票",
  receipt: "收据",
  contract: "合同",
  statement: "对账单",
  resume: "简历",
  report: "报告",
  general: "通用文档",
}

export const SKILL_LABELS = {
  document_reader: "读取文档",
  document_counter: "统计文档",
  document_summarizer: "总结文档",
  document_reviser: "修订草稿",
  esg_material_checker: "检查 ESG 材料",
  esg_standard_selector: "选择 ESG 标准",
  esg_disclosure_mapper: "映射 ESG 披露主题",
  esg_disclosure_matrix_builder: "构建 ESG 披露矩阵",
  esg_kpi_extractor: "提取 ESG 指标",
  esg_data_request_builder: "生成 ESG 补资料清单",
  esg_evidence_linker: "链接 ESG 证据",
  esg_report_outline_builder: "生成 ESG 报告大纲",
  esg_report_writer: "生成 ESG 报告",
  excel_role_classifier: "识别 Excel 角色",
  calculation_planner: "规划表格计算",
  spreadsheet_calculator: "表格计算",
  table_mapping_preview: "预览填表映射",
  table_filler: "按要求填表",
  table_data_transfer: "源表写入目标表",
  fill_validator: "校验填表结果",
}

const LOG_KIND_LABELS = {
  system: "系统步骤",
  checkpoint: "人工确认",
  skill: "技能执行",
}

const AGENT_MODE_LABELS = {
  auto: "自动",
  on: "开启",
  off: "关闭",
}

const EXECUTOR_LABELS = {
  workflow_system: "工作流系统",
  human_review: "人工确认",
  local_skill: "本地技能",
  model_api_agent: "模型 API Agent",
  openai_agent: "模型 API Agent",
  agent: "Agent",
}

export function mapIntentLabel(intentType) {
  return INTENT_LABELS[intentType] || intentType || "-"
}

export function mapIntentNames(intentTypes) {
  if (!Array.isArray(intentTypes) || !intentTypes.length) {
    return "-"
  }
  return intentTypes.map((intentType) => mapIntentLabel(intentType)).join("、")
}

export function mapDocumentKinds(kinds) {
  if (!Array.isArray(kinds) || !kinds.length) {
    return "-"
  }
  return kinds.map((kind) => DOCUMENT_KIND_LABELS[kind] || kind).join("、")
}

export function mapSkillName(skillName) {
  return SKILL_LABELS[skillName] || skillName || "-"
}

export function mapSkillNames(skillNames) {
  if (!Array.isArray(skillNames) || !skillNames.length) {
    return "-"
  }
  return skillNames.map((skillName) => mapSkillName(skillName)).join("、")
}

export function mapAgentMode(mode) {
  return AGENT_MODE_LABELS[mode] || mode || "-"
}

export function mapLogKind(kind) {
  return LOG_KIND_LABELS[kind] || kind || "-"
}

export function mapExecutorLabel(executor) {
  return EXECUTOR_LABELS[executor] || executor || "-"
}

export function mapConfirmationType(type) {
  const labels = {
    table_mapping: "表格映射确认",
    esg_report_generation: "ESG 报告生成确认",
    risk_step: "高影响步骤确认",
    plan_review: "执行计划复核",
  }
  return labels[type] || "人工确认"
}

export function formatList(values, formatter = (value) => value) {
  if (!Array.isArray(values) || !values.length) {
    return "-"
  }
  return values.map((value) => formatter(value)).join("、")
}

export function formatDateTime(value) {
  if (!value) {
    return "-"
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return String(value)
  }

  return date.toLocaleString("zh-CN", { hour12: false })
}

export function formatDuration(durationMs) {
  if (typeof durationMs !== "number") {
    return "-"
  }
  if (durationMs < 1000) {
    return `${durationMs} ms`
  }
  if (durationMs < 10000) {
    return `${(durationMs / 1000).toFixed(1)} s`
  }
  return `${Math.round(durationMs / 1000)} s`
}

export function formatCompactJson(value, limit = 140) {
  if (value === null || typeof value === "undefined") {
    return "-"
  }

  const serialized = typeof value === "string" ? value : JSON.stringify(value, null, 0)
  if (!serialized) {
    return "-"
  }

  return serialized.length > limit ? `${serialized.slice(0, limit - 1)}...` : serialized
}
