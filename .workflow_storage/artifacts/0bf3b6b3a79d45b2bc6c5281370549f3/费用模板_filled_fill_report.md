# Excel 填写报告

## 任务
读取这份 Excel，计算金额合计和平均值，并填到汇总表。

## 填写统计
- 写入模式：header_layout
- 写入单元格：2
- 保留已有值：0
- 与已有值一致：2
- 源数据为空：0
- Review 状态：skipped
- Review 风险：unknown
- Review 阻断：False

## 填写记录
| 序号 | 状态 | 填写位置 | 填写数据 | 指标 | 数据来源 | 决策来源 | 风险 | 说明 |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | written | 汇总表 / B3 | 651.6 | sum | 费用模板.xlsx / 明细 / 金额 | auto | low | 已在工作表“汇总表”的 B3 写入值（标签“sum”）。 |
| 2 | kept_existing | 汇总表 / A3 | sum | sum | 费用模板.xlsx / 明细 / 金额 | auto | low | 工作表“汇总表”的 A3 已有相同值，无需重复写入。 |
| 3 | written | 汇总表 / B4 | 325.8 | avg | 费用模板.xlsx / 明细 / 金额 | auto | low | 已在工作表“汇总表”的 B4 写入值（标签“avg”）。 |
| 4 | kept_existing | 汇总表 / A4 | avg | avg | 费用模板.xlsx / 明细 / 金额 | auto | low | 工作表“汇总表”的 A4 已有相同值，无需重复写入。 |