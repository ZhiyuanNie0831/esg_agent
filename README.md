# agent_v0

`agent_v0` 是一个本地运行的工作流 agent 原型，后端使用 FastAPI，前端使用原生 ES Modules。

项目当前的核心目标是 **Excel 自动填表**：用户上传一份或多份数据源表格，再上传一份需要填写的目标模板，agent 自动判断哪里需要填写、应该填写什么，并生成可下载的回填结果。需要填写的数量可以是 1 个，也可以是 200 个以上。

除了 Excel 填表，项目也包含文档读取、摘要、修订、ESG 材料检查、ESG 披露矩阵、后台作业、人工确认、产物下载等工作流能力。

## 目录

- [项目定位](#项目定位)
- [项目如何运作](#项目如何运作)
- [核心工作流](#核心工作流)
- [核心功能](#核心功能)
- [Excel 自动填表](#excel-自动填表)
- [ESG 报告生成](#esg-报告生成)
- [Review 交叉检查](#review-交叉检查)
- [快速开始](#快速开始)
- [环境变量](#环境变量)
- [项目结构](#项目结构)
- [API 一览](#api-一览)
- [常用请求示例](#常用请求示例)
- [前端结构](#前端结构)
- [后端结构](#后端结构)
- [测试](#测试)
- [如何新增功能](#如何新增功能)
- [边界与注意事项](#边界与注意事项)
- [排错](#排错)

## 项目定位

这个项目不是单纯的聊天页面，而是一个可以执行结构化任务的工作流系统。

它主要做四件事：

1. 接收用户任务和上传材料。
2. 把材料解析成统一的文档结构。
3. 根据任务自动选择并执行合适的 skill。
4. 在高风险步骤前暂停，等待人工确认后继续执行。

当前最重要的业务闭环是：

```text
上传数据源 Excel + 上传待填模板 Excel
        |
        v
识别源表和模板角色
        |
        v
理解任务并规划计算/填表步骤
        |
        v
从数据源中计算或抽取结果
        |
        v
预览目标 sheet/cell 填位
        |
        v
调用 review agent 交叉检查
        |
        v
人工确认或修正填位
        |
        v
写回目标 Excel 模板
        |
        v
校验写入结果并生成下载产物
```

## 项目如何运作

项目可以理解为一个“前端操作台 + FastAPI 工作流引擎 + 一组可插拔 skill + 可选模型 API”的系统。

整体数据流如下：

```text
浏览器页面
  |
  | 1. 上传文件 / 输入任务 / 选择是否人工确认
  v
FastAPI 路由层
  |
  | 2. 解析请求，调用 workflow service
  v
WorkflowAgentService
  |
  | 3. 标准化文档、识别意图、检查缺失材料
  v
WorkflowPlanningService
  |
  | 4. 生成执行计划，选择 skill 顺序
  v
WorkflowExecutionService
  |
  | 5. 按计划执行本地 skill，必要时调用模型 API
  v
WorkflowSummaryService
  |
  | 6. 汇总结果、证据、下载文件和调试 artifacts
  v
浏览器页面展示结果
```

### 1. 前端只负责操作和展示

前端在 `app/static/` 下，没有构建步骤，浏览器直接加载原生 ES Modules。

主要职责：

- 上传文件到 `/api/workflow/uploads`。
- 创建或读取 session。
- 把用户任务、上传文档、人工确认选项提交给 `/plan`、`/execute` 或 `/jobs`。
- 展示计划、执行日志、证据、下载文件、Excel 填位确认面板和 ESG 报告结果。
- 在人工确认阶段提交用户修改后的 `planOverrides`。

前端不直接做业务判断。Excel 填位、ESG 报告、OCR、review 交叉检查都在后端完成。

### 2. 上传文件会被转成统一文档结构

用户上传文件后，后端会把不同格式统一包装成 `WorkflowDocument`：

```text
原始文件
  |
  v
parse_uploaded_bytes()
  |
  v
WorkflowDocument
  |
  |-- contentText: 提取出的正文
  |-- ocrText: OCR 结果
  |-- segments: 带来源位置的片段
  |-- structuredData: Excel sheet、表头、行列、layout、workbook token
```

不同文件格式走不同 parser：

| 文件类型 | 处理方式 |
| --- | --- |
| Excel / CSV | 提取 sheet、表头、数据行、数字列、模板 layout、原始 workbook token |
| PDF | 先文本解析，必要时走 OCR |
| 图片 | 走 OCR |
| Word / PPT | 提取段落或幻灯片文本 |
| ZIP | 安全解包后解析内部文件 |
| 文本类文件 | 直接解码并切分片段 |

这些标准化文档会用于后续意图识别、计划生成、skill 执行和证据追溯。

### 3. Session 保存一次工作流的上下文

session 是前端和后端之间的工作区状态。

它会保存：

- 已上传并解析的文档。
- 最近一次任务文本。
- 最近一次 plan 结果。
- 最近一次 execute 结果。
- 最近一个后台 job ID。

典型用法是：

```text
POST /api/workflow/sessions
  -> 得到 sessionId

POST /api/workflow/uploads
  -> 带 sessionId 上传文件

POST /api/workflow/jobs
  -> 带 sessionId 执行任务
```

如果执行请求里的 `documents` 为空，但传了 `sessionId`，后端可以从 session 中读取已经上传的文档。

### 4. 意图识别决定要用哪些 skill

`WorkflowIntentionService` 会分析用户任务，输出：

- `intentType`：主意图，例如总结、修订、统计、缺件检查、审核。
- `detectedIntentTypes`：复合意图列表。
- `documentRequired`：是否依赖上传材料。
- `requiredDocumentKinds`：缺哪些材料类型。
- `recommendedSkills`：推荐执行哪些 skill。

它有两层能力：

| 层级 | 说明 |
| --- | --- |
| 本地规则 | 根据关键词、文件类型和已上传材料做稳定判断 |
| 模型 agent | 如果 `MODEL_API_AGENT_ENABLED=true` 且 API key 已配置，会让模型辅助判断复杂任务 |

如果模型不可用，但 `localFallbackEnabled=true`，系统会继续使用本地规则。

### 5. Planner 把 skill 变成可执行计划

`WorkflowPlanningService` 会把推荐 skill 转成 `PlanStep` 列表。

每个步骤包含：

| 字段 | 说明 |
| --- | --- |
| `stepId` | 稳定步骤 ID，人工确认和重跑时使用 |
| `stepNumber` | 步骤顺序 |
| `title` / `description` | 前端展示用文案 |
| `skill` | 需要执行的 skill 名称 |
| `checkpoint` | 是否是人工确认点 |
| `requiresApproval` | 是否需要审批 |
| `dependsOn` | 依赖的前置步骤 |
| `inputs` | 传给 skill 的结构化输入 |

Planner 还会自动补全一些关键步骤。

例如 Excel 填表请求如果识别到 `table_filler`，计划会自动补齐：

```text
excel_role_classifier
calculation_planner
spreadsheet_calculator
table_mapping_preview
approval
table_filler
fill_validator
```

ESG 报告生成请求如果识别到 `esg_report_writer`，计划会自动形成：

```text
esg_standard_selector
esg_disclosure_mapper
esg_disclosure_matrix_builder
esg_kpi_extractor
esg_evidence_linker
esg_report_outline_builder
approval
esg_report_writer
```

### 6. Executor 按步骤执行 skill

`WorkflowExecutionService` 是真正执行计划的地方。

执行时会给每个 skill 一个 `SkillExecutionContext`，里面包含：

- 当前任务 `task`。
- 意图分析 `intention`。
- 标准化文档 `documents`。
- 当前步骤输入 `inputs`。
- 上游 skill 的结果 `previous_results`。
- 可选模型 agent `agent_runtime`。
- 本地回退开关 `local_fallback_enabled`。

skill 只需要实现一个统一入口：

```python
def execute(self, context: SkillExecutionContext) -> dict[str, object]:
    ...
```

每个 skill 的输出必须是可 JSON 序列化的 dict。后续步骤可以通过 `context.previous_results` 读取它。

### 7. 模型 API 是可选增强，不是唯一执行核心

项目不是把所有事情都丢给模型做。

当前设计是：

| 任务 | 执行方式 |
| --- | --- |
| 文件解析、Excel 读写、artifact 存储、job 状态 | 本地确定性代码 |
| Excel 单元格实际写入 | 本地 `openpyxl` |
| Excel 填位候选、模板扫描、审计记录 | 本地规则为主 |
| 意图识别、摘要、文稿修订、ESG 报告正文 | 可用模型 API 增强 |
| Review 交叉检查 | 独立 review 模型 API |

这样做的好处是：文件写入和关键状态不会由模型直接操作，模型只负责理解、生成和审查；真正的写文件动作由后端可测试代码执行。

### 8. 人工确认用于控制高风险步骤

一些步骤会自动进入人工确认：

- `document_reviser`：会生成正式文稿。
- `table_filler`：会写回 Excel 模板。
- `esg_report_writer`：会生成面向客户的正式报告草稿。
- 用户显式勾选 `manualConfirm`。
- Excel 填位存在低置信度候选。

后台 job 遇到确认点时会变成：

```text
awaiting_confirmation
```

前端展示预览结果，用户确认后调用：

```text
POST /api/workflow/jobs/{job_id}/approve
```

如果用户修改了 Excel 填位，修改会放进 `planOverrides.stepInputOverrides`，后端审批后从暂停位置继续执行。

### 9. 后台 job 适合长任务

项目支持两种执行方式：

| 方式 | 接口 | 适合场景 |
| --- | --- | --- |
| 同步执行 | `POST /api/workflow/execute` | 快速任务、测试、简单文档处理 |
| 后台作业 | `POST /api/workflow/jobs` | Excel 填表、OCR、ESG 报告、需要人工确认的任务 |

后台作业会保存：

- 当前状态。
- 执行计划。
- 执行日志。
- 已完成 skill 结果。
- 最终输出。
- 错误信息。

如果需要从某一步重跑，可以调用：

```text
POST /api/workflow/jobs/{job_id}/rerun
```

### 10. 最终输出由 summary service 统一整理

执行结束后，`WorkflowSummaryService` 会把所有 skill 输出汇总成 `WorkflowFinalOutput`：

| 字段 | 说明 |
| --- | --- |
| `summaryText` | 给用户看的最终总结 |
| `revisedDocument` | 主文稿，例如 ESG 报告 Markdown、修订稿或填表结果表 |
| `nextActions` | 下一步建议 |
| `evidence` | 证据出处 |
| `downloads` | 可下载文件 |
| `artifacts` | 结构化调试信息、执行轨迹、技能结果 |

如果 skill 生成了 `exportFiles`，summary service 会把文件写入 artifact store，并返回下载链接：

```text
/api/workflow/artifacts/{artifact_id}
```

### 11. 两条核心业务链路

Excel 自动填表链路：

```text
上传源表和模板
  -> 解析 workbook 结构和原始 token
  -> 识别源表/模板角色
  -> 规划并执行表格计算
  -> 预览目标 sheet/cell
  -> review agent 交叉检查
  -> 人工确认或修正
  -> 本地写回 workbook
  -> 校验写入结果
  -> 输出 Excel 下载文件
```

ESG 报告生成链路：

```text
上传 ESG 材料
  -> 解析文本、表格、OCR 和片段
  -> 选择 ESG 标准
  -> 构建披露主题矩阵
  -> 抽取 KPI
  -> 建立证据索引
  -> 生成报告大纲
  -> 人工确认矩阵/证据/字数
  -> 生成 ESG 报告 Markdown
  -> 输出报告下载文件
```

## 核心工作流

后端把一次请求拆成几个阶段：

| 阶段 | 说明 | 主要模块 |
| --- | --- | --- |
| 上传解析 | 读取 Excel、PDF、Word、图片、文本等文件，转成 `WorkflowDocument` | `app/services/workflow/uploads/` |
| 输入标准化 | 整理文档文本、结构化表格、片段和来源信息 | `app/services/workflow/input.py` |
| 意图识别 | 判断用户想做填表、摘要、修订、检查还是通用任务 | `app/services/workflow/intention.py` |
| 缺失材料检查 | 判断当前材料是否足够执行任务 | `app/services/workflow/document_check.py` |
| 计划生成 | 选择 skill 并生成可执行步骤 | `app/services/workflow/planning.py` |
| 执行 | 按步骤运行 skill，记录日志和产物 | `app/services/workflow/execution.py` |
| 人工确认 | 对高风险或需审批步骤暂停，允许用户修改输入 | `app/services/workflow/job_resume.py` |
| 结果汇总 | 生成最终摘要、证据、下载文件和 artifact | `app/services/workflow/summary.py` |

## 核心功能

### Excel 自动填表

- 自动识别哪份 Excel 更像数据源，哪份更像待填模板。
- 支持从数据源表格中做求和、平均值、最大值、最小值、计数、比例、同比、环比等计算。
- 支持将计算结果映射到目标模板中的具体 `sheet` 和 `cell`。
- 支持数量不固定的填表任务，从单个指标到上百个指标都走同一套流程。
- 支持结构化表格模板和“标签 + 空白值”的表单式模板。
- 支持人工确认时修改目标 sheet、目标 cell、写入策略或跳过某项。
- 支持导出已回填的 Excel，并返回写入审计记录。
- 支持同步生成 Excel 填写报告，记录填写数据、填写位置和数据来源。

### Review 交叉检查

- 使用独立的 review 模型 API 检查填位是否可靠。
- 交叉检查不会直接写文件，只输出风险判断和建议。
- 如果风险为 high，并且开启 `MODEL_API_REVIEW_BLOCK_ON_HIGH_RISK=true`，系统会阻止自动写入。
- review API 调用失败或返回非法 JSON 时，也会根据配置决定是否阻断。

### 文档工作流

- 支持文档读取、统计、摘要和修订。
- 支持从原始材料中保留证据片段，便于追溯结果来源。
- 支持 PDF、图片 OCR、Word、PPT、邮件、文本、CSV、Excel、ZIP 等输入。

### ESG 工作流

- 支持 ESG 材料覆盖度检查。
- 支持选择披露标准，例如 GRI、ISSB、ESRS 或本地交易所方向。
- 支持生成披露主题映射、披露矩阵、KPI 抽取、补资料清单、证据索引和报告大纲。
- 支持根据上传材料生成一份 ESG 报告正文，目标字数从客户任务中自动识别。
- 报告生成前会先完成披露矩阵、大纲和证据索引，进入人工确认后再生成正式草稿。

### 作业与会话

- 支持同步执行：`POST /api/workflow/execute`。
- 支持后台作业：`POST /api/workflow/jobs`。
- 支持作业暂停、审批后继续、从指定步骤重跑。
- 支持 session 保存上传材料、最近计划、最近执行结果和最近 job。
- 支持 artifact 持久化下载，避免大文件直接塞进响应体。

## Excel 自动填表

### 输入要求

最典型的输入是两类 Excel：

| 文件类型 | 作用 |
| --- | --- |
| 数据源表格 | 包含原始明细、指标值、月份、年份、部门、金额、排放量等数据 |
| 待填模板 | 包含需要填写的空白单元格、表头、指标标签或填报表格 |

用户任务可以写得自然一些，例如：

```text
请根据数据源表格，把 2025 年各部门的用电量、用水量和碳排放量填入模板。
```

也可以更明确：

```text
从 source.xlsx 里按月份汇总销售额，并填写到 template.xlsx 的月度汇总表。
```

### 执行链路

Excel 填表主要依赖这些 skill：

| 顺序 | Skill | 作用 |
| --- | --- | --- |
| 1 | `excel_role_classifier` | 判断上传的 Excel 哪份是源表，哪份是模板 |
| 2 | `calculation_planner` | 根据任务语义规划需要计算什么 |
| 3 | `spreadsheet_calculator` | 从源表中计算或抽取结果 |
| 4 | `table_mapping_preview` | 预估每个结果应该写到模板哪里 |
| 5 | `table_filler` | 在确认后写回 Excel 并生成导出文件 |
| 6 | `fill_validator` | 重新读取导出文件，检查写入和审计是否一致 |

### 模板识别方式

当前支持两类常见模板：

| 模板类型 | 示例 | 处理方式 |
| --- | --- | --- |
| 结构化表格 | 表头里有“指标、月份、结果、单位”等列 | 找到匹配行和结果列，将结果写入对应行 |
| 标签值表单 | 左侧或上方是“用电量”“收入合计”等标签，旁边是空白格 | 识别标签语义，把结果写入标签附近的空白单元格 |

标签值表单的扫描范围会根据结果数量动态扩大。少量结果会快速扫描，结果数量很多时会扩大到更多行列，适配 100 到 200 个以上填位。

### 写入策略

人工确认时，每条映射可以指定 `writePolicy`：

| 策略 | 含义 |
| --- | --- |
| `only_empty` | 默认策略，只写入空单元格，避免覆盖已有内容 |
| `allow_same` | 如果已有值与待写入值一致，可以视为成功 |
| `force_overwrite` | 强制覆盖目标单元格 |

默认使用 `only_empty`。除非非常确定模板已有值需要被替换，否则不建议使用 `force_overwrite`。

### 关键输出字段

Excel 填表结果通常会出现在 `finalOutput.artifacts.skillResults.table_filler` 中：

| 字段 | 说明 |
| --- | --- |
| `rows` | 计算后准备填写的结构化结果行 |
| `filledTableMarkdown` | 给前端展示的 Markdown 表格 |
| `fillReportMarkdown` | Excel 填写报告，记录每条填写数据、目标位置和来源 |
| `fillReportRows` | 填写报告的结构化逐项记录 |
| `exportFiles` | 导出的 Excel 文件信息 |
| `fillAudit` | 每个单元格的写入审计记录 |
| `fillStats` | 写入数量、保留已有值数量、跳过数量等统计 |
| `crossCheck` | review 交叉检查结果 |

填写报告会作为 Markdown 下载文件出现在 `exportFiles` 和 `finalOutput.downloads` 中，文件名通常类似：

```text
template_filled_fill_report.md
```

报告包含：

- 本次任务和填写统计。
- 每条填写记录的状态。
- 目标位置，例如 `汇总表 / B12`。
- 写入值或保留值。
- 数据来源，例如 `source.xlsx / 明细 / 金额`。
- 决策来源、风险等级和审计说明。

预览阶段的候选填位通常在 `table_mapping_preview.mappingCandidates` 中：

| 字段 | 说明 |
| --- | --- |
| `mappingId` | 候选映射 ID，人工确认时用它定位同一条结果 |
| `metric` | 指标或结果名称 |
| `value` | 准备写入的值 |
| `sheet` | 目标 sheet |
| `cell` | 目标 cell |
| `confidence` | 本地识别置信度 |
| `riskLevel` | 本地风险等级 |
| `requiresConfirmation` | 是否必须人工确认 |
| `reviewRiskLevel` | review agent 给出的风险等级 |
| `reviewIssue` | review agent 给出的风险说明 |
| `reviewSuggestedSheet` | review agent 建议的 sheet |
| `reviewSuggestedCell` | review agent 建议的 cell |

## ESG 报告生成

新增的 `esg_report_writer` skill 可以根据上传材料自动生成 ESG 报告正文。客户在任务中直接提出字数要求即可，例如：

```text
请根据这些材料生成一份 5000 字 ESG 报告。
```

也支持类似表达：

```text
请写一份约 1.5 万字的 ESG report。
请生成 1500-2000 字的 ESG 报告初稿。
```

报告生成链路通常是：

| 顺序 | Skill | 作用 |
| --- | --- | --- |
| 1 | `esg_standard_selector` | 判断报告应优先参考的披露标准 |
| 2 | `esg_disclosure_mapper` | 把材料映射到 ESG 披露主题 |
| 3 | `esg_disclosure_matrix_builder` | 形成 covered / weak / missing 披露矩阵 |
| 4 | `esg_kpi_extractor` | 抽取可披露 KPI 和来源 |
| 5 | `esg_evidence_linker` | 建立 claim 到材料位置的证据索引 |
| 6 | `esg_report_outline_builder` | 生成报告大纲 |
| 7 | `approval` | 人工确认矩阵、大纲、证据和字数要求 |
| 8 | `esg_report_writer` | 生成 ESG 报告 Markdown 正文和下载文件 |

`esg_report_writer` 会优先调用主模型 API 生成报告。如果模型 API 不可用且允许本地回退，会生成一版规则草稿。规则草稿不会编造事实，材料缺失处会保留“待补充”或缺口提示。

关键输出字段：

| 字段 | 说明 |
| --- | --- |
| `reportMarkdown` | ESG 报告 Markdown 正文 |
| `targetWordCount` | 从任务中识别出的目标字数 |
| `minWordCount` / `maxWordCount` | 允许浮动范围 |
| `estimatedWordCount` | 系统估算的当前报告字数 |
| `wordCountRequirement` | 完整字数要求解析结果 |
| `disclosureMatrix` | 生成报告时使用的披露矩阵 |
| `indicators` | 报告引用的 KPI |
| `evidenceLinks` | 报告证据索引 |
| `exportFiles` | 可下载的 Markdown 报告草稿 |

## Review 交叉检查

Excel 自动填表存在两个风险：

1. 填错位置，例如把“用电量”写到“用水量”的格子里。
2. 覆盖已有重要数据，例如模板单元格本来就有公式或旧值。

为降低风险，项目引入了一个独立的 review agent。它和主 agent 可以使用不同模型、不同 provider、不同 API key。

### 检查对象

当前 review agent 会检查两类写入计划：

| 场景 | 服务 |
| --- | --- |
| 自动填表候选位置 | `TableFillMappingCrossCheckService` |
| 源表到目标表的明细数据转移 | `TableDataTransferCrossCheckService` |

### 交叉检查结果

`crossCheck` 的典型结构如下：

```json
{
  "enabled": true,
  "provider": "openai",
  "providerLabel": "OpenAI",
  "model": "gpt-5.4-mini",
  "status": "completed",
  "approved": true,
  "riskLevel": "low",
  "blockWrite": false,
  "issues": [],
  "suggestions": [],
  "candidateReviews": []
}
```

状态说明：

| 字段 | 含义 |
| --- | --- |
| `enabled` | review API 是否已启用且 key 可用 |
| `status` | `skipped`、`completed`、`error` 或 `invalid_response` |
| `approved` | review agent 是否同意当前计划 |
| `riskLevel` | `low`、`medium`、`high` 或 `unknown` |
| `blockWrite` | 是否阻断最终写入 |
| `issues` | 全局问题列表 |
| `suggestions` | 全局建议列表 |
| `candidateReviews` | 针对具体 `mappingId` 的风险反馈 |

### 阻断规则

如果配置如下：

```env
MODEL_API_REVIEW_ENABLED=true
MODEL_API_REVIEW_BLOCK_ON_HIGH_RISK=true
```

则以下情况会阻断写入：

- review agent 判断 `riskLevel=high`。
- review agent 返回 `approved=false`。
- review API 调用失败，并且系统按高风险策略处理失败。
- review API 返回非法 JSON，并且系统按高风险策略处理失败。

阻断后不会写入 Excel，但响应里会保留 `crossCheck`、`fillAudit` 和摘要说明，方便用户修改后重新确认。

## 快速开始

### 1. 创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

然后编辑 `.env`，至少配置主模型 API：

```env
MODEL_API_PROVIDER=openai
MODEL_API_PROVIDER_LABEL=OpenAI
MODEL_API_PROTOCOL=responses
MODEL_API_KEY=your_api_key
MODEL_API_BASE_URL=https://api.openai.com/v1
MODEL_API_MODEL=gpt-5.5
MODEL_API_AGENT_ENABLED=true
```

如果需要图片/PDF OCR，配置 OCR：

```env
MODEL_API_OCR_ENABLED=true
MODEL_API_OCR_KEY=your_ocr_api_key
MODEL_API_OCR_MODEL=gpt-5.4-mini
```

如果需要 Excel 填位交叉检查，配置 review API：

```env
MODEL_API_REVIEW_ENABLED=true
MODEL_API_REVIEW_KEY=your_review_api_key
MODEL_API_REVIEW_MODEL=gpt-5.4-mini
MODEL_API_REVIEW_BLOCK_ON_HIGH_RISK=true
```

不要把真实 `.env` 提交到 git。

### 4. 启动服务

```bash
uvicorn app.main:app --reload --port 8000
```

打开：

```text
http://127.0.0.1:8000/
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

如果 8000 端口被占用，可以换一个端口：

```bash
uvicorn app.main:app --reload --port 8002
```

### 5. 健康检查

```bash
curl http://127.0.0.1:8000/health
```

健康检查会返回主模型、OCR、review、worker、数据库后端等状态。响应里只会告诉你 key 是否配置，不会返回 key 值。

## 环境变量

### 主模型 API

| 变量 | 说明 | 默认/示例 |
| --- | --- | --- |
| `MODEL_API_PROVIDER` | 主模型 provider，例如 `openai`、`dashscope`、`deepseek`、`zhipu` | `dashscope` |
| `MODEL_API_PROVIDER_LABEL` | 前端展示名 | `阿里云百炼` |
| `MODEL_API_PROTOCOL` | 请求协议，通常是 `responses` 或兼容 chat 协议 | `responses` |
| `MODEL_API_KEY` | 主模型 API key | 必填 |
| `MODEL_API_BASE_URL` | API base URL | provider 默认值 |
| `MODEL_API_MODEL` | 主模型名称 | `qwen-plus` |
| `MODEL_API_TIMEOUT_SECONDS` | 主模型超时时间 | `90` |
| `MODEL_API_REASONING_EFFORT` | 常规推理强度 | `medium` |
| `MODEL_API_HEAVY_REASONING_EFFORT` | 重推理任务强度 | `high` |
| `MODEL_API_AGENT_ENABLED` | 是否启用模型 agent | `true` |

项目也兼容部分旧 OpenAI 变量，例如 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`。推荐新配置统一使用 `MODEL_API_*`。

### OCR API

| 变量 | 说明 | 默认/示例 |
| --- | --- | --- |
| `MODEL_API_OCR_PROVIDER` | OCR provider，未配置时默认跟主模型一致 | 同主模型 |
| `MODEL_API_OCR_PROVIDER_LABEL` | OCR 展示名 | provider 展示名 |
| `MODEL_API_OCR_PROTOCOL` | OCR 请求协议 | provider 默认值 |
| `MODEL_API_OCR_KEY` | OCR API key，未填时可复用 `MODEL_API_KEY` | 可选 |
| `MODEL_API_OCR_BASE_URL` | OCR base URL | provider 默认值 |
| `MODEL_API_OCR_ENABLED` | 是否启用 OCR | `true` |
| `MODEL_API_OCR_MODEL` | OCR 模型 | 同主模型或指定视觉模型 |
| `MODEL_API_OCR_TIMEOUT_SECONDS` | OCR 超时时间 | `180` |
| `MODEL_API_OCR_MAX_OUTPUT_TOKENS` | OCR 最大输出 token | `4000` |
| `MODEL_API_OCR_IMAGE_DETAIL` | 图片细节等级，支持 `auto`、`low`、`high` | `high` |
| `MODEL_API_OCR_PDF_MODE` | PDF OCR 模式，支持 `off`、`fallback`、`hybrid` | `hybrid` |
| `MODEL_API_OCR_PDF_PAGES_PER_REQUEST` | PDF OCR 每次请求页数 | `1` |

### Review API

| 变量 | 说明 | 默认/示例 |
| --- | --- | --- |
| `MODEL_API_REVIEW_PROVIDER` | review provider | 自动推断 |
| `MODEL_API_REVIEW_PROVIDER_LABEL` | review 展示名 | provider 展示名 |
| `MODEL_API_REVIEW_PROTOCOL` | review 请求协议 | provider 默认值 |
| `MODEL_API_REVIEW_KEY` | review API key | 建议配置 |
| `MODEL_API_REVIEW_BASE_URL` | review base URL | provider 默认值 |
| `MODEL_API_REVIEW_ENABLED` | 是否启用 review agent | `true` |
| `MODEL_API_REVIEW_MODEL` | review 模型 | `gpt-5.4-mini` 或 provider 默认 |
| `MODEL_API_REVIEW_TIMEOUT_SECONDS` | review 超时时间 | `60` |
| `MODEL_API_REVIEW_MAX_OUTPUT_TOKENS` | review 最大输出 token | `1200` |
| `MODEL_API_REVIEW_BLOCK_ON_HIGH_RISK` | 高风险或 review 失败时是否阻断写入 | `true` |

也支持 OpenAI review 别名：

```env
OPENAI_REVIEW_API_KEY=
OPENAI_REVIEW_MODEL=gpt-5.4-mini
OPENAI_REVIEW_BASE_URL=https://api.openai.com/v1
```

### 存储与后台作业

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy 数据库连接 | `.workflow_storage/workflow.db` |
| `WORKFLOW_STORAGE_DIR` | 本地工作流存储目录 | `.workflow_storage` |
| `WORKFLOW_WORKER_COUNT` | 后台 job worker 数量 | `2` |
| `WORKFLOW_JOB_HEARTBEAT_TIMEOUT_SECONDS` | job 心跳超时时间 | `300` |
| `WORKFLOW_ZIP_ENTRY_LIMIT` | ZIP 解包文件数量上限 | `50` |
| `WORKFLOW_ZIP_TOTAL_SIZE_LIMIT_BYTES` | ZIP 解包总大小上限 | `104857600` |

### 上传解析限制

这些变量为 `0` 或空时表示不限制：

| 变量 | 说明 |
| --- | --- |
| `WORKFLOW_UPLOAD_TEXT_CHAR_LIMIT` | 文本文档保留字符数上限 |
| `WORKFLOW_UPLOAD_TABLE_ROW_LIMIT` | 表格解析行数上限 |
| `WORKFLOW_UPLOAD_TABLE_COLUMN_LIMIT` | 表格解析列数上限 |
| `WORKFLOW_UPLOAD_PDF_PAGE_LIMIT` | PDF 解析页数上限 |

## 项目结构

```text
agent_v0/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── routes/
│   │   ├── workflow.py
│   │   └── workflow_api/
│   ├── schemas/
│   │   └── workflow.py
│   ├── services/
│   │   ├── model_api.py
│   │   ├── model_api_profiles.py
│   │   └── workflow/
│   │       ├── service.py
│   │       ├── planning.py
│   │       ├── execution.py
│   │       ├── job_store.py
│   │       ├── session_store.py
│   │       ├── uploads/
│   │       ├── skills/
│   │       └── table_fill/
│   └── static/
│       ├── index.html
│       ├── styles.css
│       ├── workflow_bundle.txt
│       └── js/
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```

## API 一览

项目当前主要有 12 个工作流 API，外加健康检查和前端页面。

### 基础接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | 前端页面 |
| `GET` | `/health` | 服务、模型、OCR、review、worker 状态 |
| `GET` | `/workflow-bundle` | 前端入口脚本 |
| `GET` | `/docs` | FastAPI OpenAPI 文档 |

### 工作流接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/workflow/skills` | 获取当前注册的 skill |
| `POST` | `/api/workflow/uploads` | 上传并解析材料 |
| `POST` | `/api/workflow/plan` | 只规划，不执行 |
| `POST` | `/api/workflow/execute` | 同步执行工作流 |
| `POST` | `/api/workflow/jobs` | 创建后台 job |
| `GET` | `/api/workflow/jobs/{job_id}` | 查询 job 状态 |
| `POST` | `/api/workflow/jobs/{job_id}/approve` | 审批暂停中的 job 并继续执行 |
| `POST` | `/api/workflow/jobs/{job_id}/rerun` | 从指定步骤重跑 job |
| `GET` | `/api/workflow/artifacts/{artifact_id}` | 下载产物 |
| `POST` | `/api/workflow/sessions` | 创建 session |
| `GET` | `/api/workflow/sessions/{session_id}` | 读取 session |
| `DELETE` | `/api/workflow/sessions/{session_id}` | 删除 session |

## 常用请求示例

### 创建 session

```bash
curl -X POST http://127.0.0.1:8000/api/workflow/sessions
```

### 上传 Excel 文件

```bash
curl -X POST http://127.0.0.1:8000/api/workflow/uploads \
  -F "sessionId=SESSION_ID" \
  -F "files=@source.xlsx" \
  -F "files=@template.xlsx"
```

上传接口返回的 `documents` 或 `mergedDocuments` 可以直接传给 `/plan`、`/execute` 或 `/jobs`。

### 本地 Excel 填表样例

项目内置了一个 30 个空缺的 Excel 自动填表示例：

```text
samples/excel_fill_30_blanks/
```

其中：

| 文件 | 说明 |
| --- | --- |
| `01_source_esg_metrics_2025.xlsx` | 源数据表，包含 30 个 ESG 指标值 |
| `02_target_esg_template_30_blanks.xlsx` | 待填模板，`填报模板!C4:C33` 共 30 个空缺 |
| `03_expected_filled_result.xlsx` | 标准答案，用于比对输出 |

测试时上传前两个文件，并要求 agent 按 `指标编码` 或 `ESG指标` 把源表 `填报值` 写入目标模板 `C4:C33`。

### 只生成计划

```bash
curl -X POST http://127.0.0.1:8000/api/workflow/plan \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "SESSION_ID",
    "task": "请根据数据源表格填写模板",
    "documents": [],
    "manualConfirm": true,
    "agentMode": "on",
    "localFallbackEnabled": true
  }'
```

### 创建后台填表 job

```bash
curl -X POST http://127.0.0.1:8000/api/workflow/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "SESSION_ID",
    "task": "请根据数据源表格填写模板",
    "documents": [],
    "manualConfirm": true,
    "approved": false,
    "agentMode": "on",
    "localFallbackEnabled": true,
    "preferredSkills": [
      "excel_role_classifier",
      "calculation_planner",
      "spreadsheet_calculator",
      "table_mapping_preview",
      "table_filler",
      "fill_validator"
    ],
    "planOverrides": {
      "disabledStepIds": [],
      "stepInputOverrides": {}
    }
  }'
```

如果请求里 `documents` 为空，但 `sessionId` 下已有上传材料，后端会从 session 里读取已上传文档。

### 查询 job

```bash
curl http://127.0.0.1:8000/api/workflow/jobs/JOB_ID
```

job 状态可能是：

| 状态 | 说明 |
| --- | --- |
| `queued` | 已入队 |
| `running` | 正在执行 |
| `awaiting_confirmation` | 已暂停，等待人工确认 |
| `completed` | 已完成 |
| `blocked` | 业务规则阻断 |
| `failed` | 执行失败 |

### 审批并提交人工修正

当 job 进入 `awaiting_confirmation` 后，前端会展示 `table_mapping_preview` 的候选填位。用户可以修改 `sheet`、`cell`、`writePolicy` 或关闭某条映射。

审批请求示例：

```bash
curl -X POST http://127.0.0.1:8000/api/workflow/jobs/JOB_ID/approve \
  -H "Content-Type: application/json" \
  -d '{
    "approved": true,
    "planOverrides": {
      "disabledStepIds": [],
      "stepInputOverrides": {
        "TABLE_FILLER_STEP_ID": {
          "requireConfirmedCandidates": true,
          "manualMappings": [
            {
              "mappingId": "map_1",
              "enabled": true,
              "metric": "用电量合计",
              "sheet": "填报表",
              "cell": "C12",
              "writePolicy": "only_empty",
              "value": 12345
            }
          ]
        }
      }
    }
  }'
```

`TABLE_FILLER_STEP_ID` 不是固定值，需要从 job 的 `plan` 里找到 `skill == "table_filler"` 的那一步。

### 下载产物

执行完成后，响应里的下载项通常包含：

```json
{
  "label": "Excel 回填结果",
  "filename": "filled_template.xlsx",
  "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "artifactId": "...",
  "downloadUrl": "/api/workflow/artifacts/..."
}
```

下载：

```bash
curl -L -o filled_template.xlsx http://127.0.0.1:8000/api/workflow/artifacts/ARTIFACT_ID
```

## 前端结构

前端没有构建步骤，直接使用浏览器原生 ES Modules。

入口关系：

```text
app/static/index.html
        |
        v
app/static/workflow_bundle.txt
        |
        v
app/static/js/app.js
```

模块划分：

| 目录 | 说明 |
| --- | --- |
| `app/static/js/api/` | 后端 API client |
| `app/static/js/components/` | 有交互行为的组件 |
| `app/static/js/config/` | 固定文案、标签、演示场景 |
| `app/static/js/core/` | DOM、HTML escape、共享状态 |
| `app/static/js/views/` | 结果、确认面板、最终输出等渲染逻辑 |

前端开发约定：

- 请求逻辑放在 `api/`。
- 可复用状态放在 `core/workflow-state.js`。
- 用户交互组件放在 `components/`。
- 结果展示放在 `views/`。
- `app.js` 只做页面组合和事件编排。

## 后端结构

### 路由层

`app/routes/workflow.py` 是聚合入口，真实路由按职责拆在 `app/routes/workflow_api/`：

| 文件 | 说明 |
| --- | --- |
| `catalog.py` | skill 目录 |
| `uploads.py` | 文件上传 |
| `planning.py` | plan 和 execute |
| `jobs.py` | 后台 job |
| `artifacts.py` | 产物下载 |
| `sessions.py` | session |
| `errors.py` | 工作流异常转 HTTP 响应 |

### 服务层

| 模块 | 说明 |
| --- | --- |
| `service.py` | 总编排入口，串联规划、执行、job、session |
| `agent_runtime.py` | 模型 agent 调用封装 |
| `input.py` | 文档输入标准化 |
| `intention.py` | 意图分析 |
| `planning.py` | 执行计划生成 |
| `execution.py` | skill 执行器 |
| `summary.py` | 最终输出汇总 |
| `job_store.py` | 后台 job 存储 |
| `session_store.py` | session 状态存储 |
| `file_store.py` | artifact 文件存储 |
| `uploads/` | 文件解析和上传缓存 |
| `skills/` | 所有可执行 skill |
| `table_fill/` | Excel 写回、候选映射、review 交叉检查、结果行工具 |

### Skill 注册表

默认注册的 skill 在 `app/services/workflow/skills/__init__.py`。

当前内置 skill：

| Skill | 说明 |
| --- | --- |
| `document_reader` | 读取标准化文档 |
| `document_counter` | 统计文档 |
| `document_summarizer` | 总结文档 |
| `document_reviser` | 修订草稿，需要审批 |
| `esg_material_checker` | 检查 ESG 材料覆盖度 |
| `esg_standard_selector` | 选择 ESG 标准 |
| `esg_disclosure_mapper` | 映射 ESG 披露主题 |
| `esg_disclosure_matrix_builder` | 构建 ESG 披露矩阵 |
| `esg_kpi_extractor` | 提取 ESG KPI |
| `esg_data_request_builder` | 生成 ESG 补资料清单 |
| `esg_evidence_linker` | 链接 ESG 证据 |
| `esg_report_outline_builder` | 生成 ESG 报告大纲 |
| `esg_report_writer` | 生成指定字数的 ESG 报告正文，需要审批 |
| `excel_role_classifier` | 识别 Excel 源表和模板 |
| `calculation_planner` | 规划表格计算 |
| `spreadsheet_calculator` | 执行表格计算 |
| `table_mapping_preview` | 预览填表映射 |
| `table_filler` | 回填 Excel，需要审批 |
| `table_data_transfer` | 源表明细写入目标表 |
| `fill_validator` | 校验填表结果 |

## 支持的上传文件

| 类型 | 扩展名 |
| --- | --- |
| 文本/配置/代码 | `.txt`、`.md`、`.csv`、`.json`、`.xml`、`.yaml`、`.log`、`.sql`、`.py`、`.js`、`.ts`、`.css` 等 |
| 图片 | `.png`、`.jpg`、`.jpeg`、`.bmp`、`.gif`、`.webp`、`.tiff`、`.heic` |
| Excel | `.xlsx`、`.xlsm`、`.xls` |
| Word | `.docx`、`.doc` |
| PowerPoint | `.pptx` |
| PDF | `.pdf` |
| 邮件 | `.eml`、`.msg` |
| 压缩包 | `.zip` |

ZIP 会按安全限制解析。Excel 会保留原始 workbook token，用于后续在原模板结构上写回。

## 测试

运行全部测试：

```bash
python -m unittest discover -s tests
```

常用定向测试：

```bash
python -m unittest tests.test_config
python -m unittest tests.test_model_api
python -m unittest tests.test_workflow
python -m unittest tests.test_app
```

测试覆盖重点：

- FastAPI 应用和健康检查。
- 模型 API profile 和配置解析。
- 工作流规划、执行、session、job。
- Excel 自动填表、人工确认、动态数量填位。
- ESG 报告生成、字数解析、人工确认和 Markdown 下载。
- review 交叉检查阻断和候选风险提示。
- 静态前端资源加载。

## 如何新增功能

### 新增一个后端 skill

1. 在 `app/services/workflow/skills/` 下创建新文件。
2. 继承 `WorkflowSkill`。
3. 实现 `name`、`title`、`description`、`input_hint`、`output_hint` 和 `execute()`。
4. 在 `app/services/workflow/skills/__init__.py` 的 `build_default_skill_registry()` 中注册。
5. 如果希望 planner 自动选中它，需要在意图分析或规划逻辑中加入关键词、任务类型或 preferred skill 支持。
6. 为新 skill 增加测试，至少覆盖成功路径和缺少输入的路径。

最小结构：

```python
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class MySkill(WorkflowSkill):
    name = "my_skill"
    title = "我的技能"
    description = "执行某个明确任务。"
    input_hint = "需要的输入"
    output_hint = "输出内容"
    tags = ("custom",)

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        return {
            "summary": "执行完成。",
            "evidence": [],
            "evidenceRefs": [],
        }
```

### 新增一个 API

1. 优先在 `app/routes/workflow_api/` 下按职责新增或扩展路由文件。
2. 数据结构放到 `app/schemas/workflow.py`，不要在路由里散落 dict。
3. 业务逻辑放服务层，路由层只负责参数接收和异常转换。
4. 在 `app/routes/workflow.py` 聚合新 router。
5. 增加 API 测试。

### 新增一个前端页面能力

1. 后端请求封装放到 `app/static/js/api/`。
2. 共享状态放到 `app/static/js/core/workflow-state.js`。
3. 用户交互放到 `app/static/js/components/`。
4. 展示逻辑放到 `app/static/js/views/`。
5. `app/static/js/app.js` 只负责串联。

## 边界与注意事项

### Excel 填位仍然需要人工确认

系统会尽量自动识别目标位置，但 Excel 模板可能非常自由，例如合并单元格、多层表头、跨 sheet 引用、隐藏行列、公式区域、同名指标等。高风险候选必须人工确认。

### Review agent 是交叉检查，不是绝对真相

review API 可以发现很多语义错误，但它仍然是模型判断。最终写入仍由本地确定性代码执行，关键任务建议保留人工确认。

### 默认不会覆盖已有值

默认 `writePolicy=only_empty`。如果目标单元格已有值，系统会保留已有值并在 `fillAudit` 中记录。

### OCR 质量取决于文件质量和模型能力

扫描件、低清图片、复杂表格 PDF 可能需要更强 OCR 模型或人工校验。

### 本项目更偏本地单机原型

当前存储默认在 `.workflow_storage`，数据库默认 SQLite。生产化部署时建议补充鉴权、权限隔离、对象存储、任务队列、日志采集和更严格的文件安全策略。

## 排错

### `/health` 显示 `apiConfigured=false`

检查 `.env` 是否有：

```env
MODEL_API_KEY=...
```

如果使用旧变量，确认：

```env
OPENAI_API_KEY=...
```

### OCR 没有生效

检查：

```env
MODEL_API_OCR_ENABLED=true
MODEL_API_OCR_KEY=...
MODEL_API_OCR_MODEL=...
```

如果 OCR key 留空，系统会尝试复用主模型 key。前提是主模型 provider 和模型支持图片或 PDF 输入。

### Review 交叉检查被跳过

检查：

```env
MODEL_API_REVIEW_ENABLED=true
MODEL_API_REVIEW_KEY=...
MODEL_API_REVIEW_MODEL=...
```

如果 `crossCheck.status=skipped`，通常是 review key 未配置或 review agent 被禁用。

### Review 阻断写入

如果 `crossCheck.blockWrite=true`，说明 review 判断风险较高，或 review 调用失败且配置要求失败即阻断。

可以做三件事：

1. 在人工确认面板修正目标 sheet/cell。
2. 检查模板中对应单元格是否已有值或公式。
3. 在确认无风险后，再使用更明确的人工映射重新审批。

### Excel 没有写入模板

常见原因：

- 没有识别到稳定模板，只生成了结果表。
- 候选映射置信度低，等待人工确认。
- 目标单元格已有值，默认策略保留已有值。
- review agent 阻断写入。
- 上传的模板不是可写入的 Excel workbook。

优先查看：

- `table_mapping_preview.mappingCandidates`
- `table_filler.fillAudit`
- `table_filler.fillStats`
- `table_filler.crossCheck`

### 端口被占用

换一个端口启动：

```bash
uvicorn app.main:app --reload --port 8002
```

### `.xls` 解析异常

项目主要通过 `openpyxl` 处理现代 Excel workbook。复杂或老旧 `.xls` 文件建议先另存为 `.xlsx`。

## 一句话总结

`agent_v0` 是一个围绕 Excel 自动填表和 ESG 报告生成搭建的本地工作流 agent：它能解析材料、规划步骤、计算结果、预览填位、生成指定字数的 ESG 报告、调用 review agent 做交叉检查、等待人工确认，并输出可下载产物。
