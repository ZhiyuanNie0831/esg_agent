"""工作流接口使用的数据模型定义。"""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

WorkflowDocumentType = Literal[
    "text",
    "pdf",
    "image",
    "excel",
    "word",
    "email",
    "note",
    "presentation",
    "archive",
    "other",
]
WorkflowIntentType = Literal["review", "count", "summarize", "revise", "check_missing", "general"]
WorkflowPlanStatus = Literal["planned", "needs_documents", "ready_to_execute"]
WorkflowExecutionStatus = Literal["awaiting_confirmation", "needs_documents", "completed", "blocked"]
WorkflowStepStatus = Literal["planned", "running", "completed", "failed", "skipped", "blocked"]
WorkflowReadinessStatus = Literal["ready", "partial", "missing"]
WorkflowLogKind = Literal["system", "checkpoint", "skill"]
WorkflowAgentMode = Literal["auto", "on", "off"]
WorkflowJobStatus = Literal["queued", "running", "awaiting_confirmation", "completed", "blocked", "failed"]


def _id() -> str:
    """生成稳定格式的默认字符串 ID。"""
    return uuid4().hex


class DocumentSegment(BaseModel):
    """一段从原始文档中提取出的内容片段，并带有轻量来源信息。"""

    segmentId: str = Field(min_length=1)
    kind: str = "paragraph"
    label: str = ""
    text: str = Field(min_length=1)
    page: int | None = None
    section: str | None = None
    sheet: str | None = None
    rowStart: int | None = None
    rowEnd: int | None = None


class WorkflowDocument(BaseModel):
    """调用方传入的一份原始文档或文本材料。"""

    documentId: str = Field(default_factory=_id, min_length=1)
    name: str = Field(min_length=1)
    type: WorkflowDocumentType = "text"
    source: str | None = None
    mimeType: str | None = None
    sizeBytes: int | None = None
    parser: str | None = None
    notes: list[str] = Field(default_factory=list)
    contentText: str | None = None
    ocrText: str | None = None
    tags: list[str] = Field(default_factory=list)
    segments: list[DocumentSegment] = Field(default_factory=list)
    structuredData: dict[str, Any] = Field(default_factory=dict)


class WorkflowContext(BaseModel):
    """调用方附带的上下文信息，便于后续扩展。"""

    caseId: str | None = None
    userId: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunRequest(BaseModel):
    """工作流规划阶段的请求体。"""

    sessionId: str | None = None
    task: str = Field(min_length=1)
    documents: list[WorkflowDocument] = Field(default_factory=list)
    manualConfirm: bool = False
    agentMode: WorkflowAgentMode = "on"
    localFallbackEnabled: bool = True
    preferredSkills: list[str] = Field(default_factory=list)
    context: WorkflowContext = Field(default_factory=WorkflowContext)


class WorkflowExecuteRequest(WorkflowRunRequest):
    """工作流执行阶段的请求体。"""

    approved: bool = False


class PreparedDocument(BaseModel):
    """标准化后的文档结构，供后续服务统一使用。"""

    documentId: str = Field(default_factory=_id, min_length=1)
    name: str
    type: WorkflowDocumentType
    source: str | None = None
    mimeType: str | None = None
    sizeBytes: int | None = None
    parser: str | None = None
    notes: list[str] = Field(default_factory=list)
    text: str
    textPreview: str
    hasUsableText: bool = True
    usedOcr: bool = False
    inferredKinds: list[str] = Field(default_factory=list)
    segments: list[DocumentSegment] = Field(default_factory=list)
    structuredData: dict[str, Any] = Field(default_factory=dict)


class IntentionAnalysis(BaseModel):
    """对用户任务的结构化理解结果。"""

    primaryGoal: str
    intentType: WorkflowIntentType
    detectedIntentTypes: list[WorkflowIntentType] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    documentRequired: bool = False
    requiredDocumentKinds: list[str] = Field(default_factory=list)
    recommendedSkills: list[str] = Field(default_factory=list)
    unsupportedPreferredSkills: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MissingDocumentCheck(BaseModel):
    """缺失材料检查结果。"""

    requiredKinds: list[str] = Field(default_factory=list)
    presentKinds: list[str] = Field(default_factory=list)
    missingKinds: list[str] = Field(default_factory=list)
    readiness: WorkflowReadinessStatus = "ready"
    advice: list[str] = Field(default_factory=list)
    complete: bool = True


class SkillDescriptor(BaseModel):
    """单个技能的可读描述。"""

    name: str
    title: str
    description: str
    inputHint: str = ""
    outputHint: str = ""
    requiresApproval: bool = False
    tags: list[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    """执行计划中的一步。"""

    stepId: str = Field(default_factory=_id, min_length=1)
    stepNumber: int
    title: str
    description: str
    skill: str | None = None
    checkpoint: str | None = None
    requiresApproval: bool = False
    status: WorkflowStepStatus = "planned"
    dependsOn: list[int] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)


class ExecutionLogEntry(BaseModel):
    """单个执行步骤的日志记录。"""

    stepId: str | None = None
    stepNumber: int
    title: str
    skill: str | None = None
    kind: WorkflowLogKind = "skill"
    executor: str | None = None
    status: WorkflowStepStatus
    message: str
    dependsOn: list[int] = Field(default_factory=list)
    inputSummary: dict[str, Any] = Field(default_factory=dict)
    outputSummary: dict[str, Any] = Field(default_factory=dict)
    startedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finishedAt: datetime | None = None
    durationMs: int | None = None
    outputPreview: str | None = None


class WorkflowEvidenceItem(BaseModel):
    """面向用户展示的一条证据项，指回原始材料。"""

    title: str
    documentId: str | None = None
    document: str
    location: str = "-"
    excerpt: str
    sourceStep: str | None = None
    segmentId: str | None = None
    page: int | None = None
    section: str | None = None
    sheet: str | None = None
    rowStart: int | None = None
    rowEnd: int | None = None
    cellRange: str | None = None


class WorkflowDownloadItem(BaseModel):
    """工作流生成的一份可下载产物。"""

    label: str
    filename: str
    mimeType: str
    artifactId: str | None = None
    downloadUrl: str | None = None
    contentBase64: str | None = None


class WorkflowFinalOutput(BaseModel):
    """最终返回给用户的工作流输出。"""

    summaryText: str
    revisedDocument: str | None = None
    nextActions: list[str] = Field(default_factory=list)
    evidence: list[WorkflowEvidenceItem] = Field(default_factory=list)
    downloads: list[WorkflowDownloadItem] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)


class WorkflowPlanResponse(BaseModel):
    """人工确认前返回的规划结果。"""

    requestId: UUID
    sessionId: str | None = None
    status: WorkflowPlanStatus
    intention: IntentionAnalysis
    preparedDocuments: list[PreparedDocument] = Field(default_factory=list)
    missingDocuments: MissingDocumentCheck
    suggestedSkills: list[SkillDescriptor] = Field(default_factory=list)
    plan: list[PlanStep] = Field(default_factory=list)
    summary: str


class WorkflowExecuteResponse(BaseModel):
    """包含执行日志和最终结果的执行响应。"""

    requestId: UUID
    sessionId: str | None = None
    status: WorkflowExecutionStatus
    intention: IntentionAnalysis
    preparedDocuments: list[PreparedDocument] = Field(default_factory=list)
    missingDocuments: MissingDocumentCheck
    plan: list[PlanStep] = Field(default_factory=list)
    logs: list[ExecutionLogEntry] = Field(default_factory=list)
    executedSkills: list[str] = Field(default_factory=list)
    finalOutput: WorkflowFinalOutput | None = None


class SkillCatalogResponse(BaseModel):
    """当前工作流引擎中已注册技能的清单。"""

    total: int
    skills: list[SkillDescriptor] = Field(default_factory=list)


class WorkflowUploadResponse(BaseModel):
    """上传文件解析完成后返回的结果。"""

    sessionId: str | None = None
    total: int
    documents: list[WorkflowDocument] = Field(default_factory=list)
    mergedDocuments: list[WorkflowDocument] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkflowSessionState(BaseModel):
    """一个工作流 session 的可恢复状态快照。"""

    sessionId: str = Field(min_length=1)
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    task: str = ""
    documents: list[WorkflowDocument] = Field(default_factory=list)
    manualConfirm: bool = False
    agentMode: WorkflowAgentMode = "on"
    localFallbackEnabled: bool = True
    preferredSkills: list[str] = Field(default_factory=list)
    context: WorkflowContext = Field(default_factory=WorkflowContext)
    latestPlanResponse: WorkflowPlanResponse | None = None
    latestExecutionResponse: WorkflowExecuteResponse | None = None
    latestJobId: str | None = None


class PlanOverrides(BaseModel):
    """执行前允许对计划做的有限修改。"""

    disabledStepIds: list[str] = Field(default_factory=list)
    stepInputOverrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CreateWorkflowJobRequest(WorkflowExecuteRequest):
    """创建后台工作流作业。"""

    planOverrides: PlanOverrides = Field(default_factory=PlanOverrides)


class ApproveWorkflowJobRequest(BaseModel):
    """审批后继续执行一个已暂停的作业。"""

    approved: bool = True
    planOverrides: PlanOverrides = Field(default_factory=PlanOverrides)


class RerunWorkflowJobRequest(BaseModel):
    """从指定步骤克隆并重跑作业。"""

    fromStepId: str = Field(min_length=1)


class WorkflowJobSnapshot(BaseModel):
    """后台作业的当前状态快照。"""

    jobId: str = Field(default_factory=_id, min_length=1)
    requestId: UUID
    sessionId: str | None = None
    status: WorkflowJobStatus
    task: str
    approved: bool = False
    request: WorkflowExecuteRequest
    planOverrides: PlanOverrides = Field(default_factory=PlanOverrides)
    plan: list[PlanStep] = Field(default_factory=list)
    intention: IntentionAnalysis | None = None
    preparedDocuments: list[PreparedDocument] = Field(default_factory=list)
    missingDocuments: MissingDocumentCheck | None = None
    logs: list[ExecutionLogEntry] = Field(default_factory=list)
    executedSkills: list[str] = Field(default_factory=list)
    finalOutput: WorkflowFinalOutput | None = None
    error: str | None = None
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completedAt: datetime | None = None
    reuseSourceJobId: str | None = None


class WorkflowSessionDeleteResponse(BaseModel):
    """删除一个 session 后返回的简单结果。"""

    ok: bool = True
    sessionId: str
