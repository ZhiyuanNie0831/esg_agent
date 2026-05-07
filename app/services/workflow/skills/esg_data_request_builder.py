"""ESG 补资料清单生成技能。"""

from app.services.workflow.esg import build_esg_data_requests, build_esg_disclosure_matrix
from app.services.workflow.skills.base import SkillExecutionContext, WorkflowSkill


class ESGDataRequestBuilderSkill(WorkflowSkill):
    """根据披露矩阵生成面向业务部门的补资料/追数清单。"""

    name = "esg_data_request_builder"
    title = "生成 ESG 补资料清单"
    description = "把 weak / missing 披露项转成数据请求，包含责任部门、优先级、需要的数据和原因。"
    input_hint = "ESG 披露矩阵"
    output_hint = "待补资料清单"
    tags = ("esg", "gap", "request")

    def execute(self, context: SkillExecutionContext) -> dict[str, object]:
        matrix_items = context.previous_results.get("esg_disclosure_matrix_builder", {}).get("disclosureMatrix", [])
        if not isinstance(matrix_items, list) or not matrix_items:
            matrix_items = build_esg_disclosure_matrix(context.documents)["matrix"]

        requests = build_esg_data_requests([item for item in matrix_items if isinstance(item, dict)])
        high_count = len([item for item in requests if item.get("priority") == "high"])
        return {
            "summary": f"已生成 {len(requests)} 条 ESG 补资料请求，其中高优先级 {high_count} 条。",
            "dataRequests": requests,
            "requestStats": {
                "total": len(requests),
                "high": high_count,
                "medium": len(requests) - high_count,
            },
        }
