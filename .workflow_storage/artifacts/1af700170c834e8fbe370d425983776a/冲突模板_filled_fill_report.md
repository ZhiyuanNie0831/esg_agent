# Excel 填写报告

## 任务
读取原始数据.xlsx 的金额，计算合计和平均值，并填到冲突模板.xlsx。

## 填写统计
- 写入模式：manual_mapping
- 写入单元格：1
- 保留已有值：0
- 与已有值一致：0
- 源数据为空：0
- Review 状态：skipped
- Review 风险：unknown
- Review 阻断：False

## 填写记录
| 序号 | 状态 | 填写位置 | 填写数据 | 指标 | 数据来源 | 决策来源 | 风险 | 说明 |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | written | 汇总页 / B2 | 651.6 | sum | 原始数据.xlsx / 报销明细 / 金额 | manual | medium | 已在工作表“汇总页”的 B2 写入值（标签“sum”）。 |
| 2 | manual_mapping_skipped | - | 325.8 | avg | 原始数据.xlsx / 报销明细 / 金额 | manual | low | 该结果已被人工标记为跳过，不会写入模板。 |