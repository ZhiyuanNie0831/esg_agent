"""默认技能注册入口。"""

from app.services.workflow.skills.calculation_planner import CalculationPlannerSkill
from app.services.workflow.skills.document_counter import DocumentCounterSkill
from app.services.workflow.skills.document_reader import DocumentReaderSkill
from app.services.workflow.skills.document_reviser import DocumentReviserSkill
from app.services.workflow.skills.document_summarizer import DocumentSummarizerSkill
from app.services.workflow.skills.excel_role_classifier import ExcelRoleClassifierSkill
from app.services.workflow.skills.esg_data_request_builder import ESGDataRequestBuilderSkill
from app.services.workflow.skills.esg_disclosure_matrix_builder import ESGDisclosureMatrixBuilderSkill
from app.services.workflow.skills.esg_disclosure_mapper import ESGDisclosureMapperSkill
from app.services.workflow.skills.esg_evidence_linker import ESGEvidenceLinkerSkill
from app.services.workflow.skills.esg_kpi_extractor import ESGKPIExtractorSkill
from app.services.workflow.skills.esg_material_checker import ESGMaterialCheckerSkill
from app.services.workflow.skills.esg_report_outline_builder import ESGReportOutlineBuilderSkill
from app.services.workflow.skills.esg_report_writer import ESGReportWriterSkill
from app.services.workflow.skills.esg_standard_selector import ESGStandardSelectorSkill
from app.services.workflow.skills.fill_validator import FillValidatorSkill
from app.services.workflow.skills.registry import WorkflowSkillRegistry
from app.services.workflow.skills.spreadsheet_calculator import SpreadsheetCalculatorSkill
from app.services.workflow.skills.table_data_transfer import TableDataTransferSkill
from app.services.workflow.skills.table_filler import TableFillerSkill
from app.services.workflow.skills.table_mapping_preview import TableMappingPreviewSkill


def build_default_skill_registry() -> WorkflowSkillRegistry:
    """构建系统默认使用的技能注册表。"""
    registry = WorkflowSkillRegistry()
    registry.register(DocumentReaderSkill())
    registry.register(DocumentCounterSkill())
    registry.register(DocumentSummarizerSkill())
    registry.register(DocumentReviserSkill())
    registry.register(ESGMaterialCheckerSkill())
    registry.register(ESGStandardSelectorSkill())
    registry.register(ESGDisclosureMapperSkill())
    registry.register(ESGDisclosureMatrixBuilderSkill())
    registry.register(ESGKPIExtractorSkill())
    registry.register(ESGDataRequestBuilderSkill())
    registry.register(ESGEvidenceLinkerSkill())
    registry.register(ESGReportOutlineBuilderSkill())
    registry.register(ESGReportWriterSkill())
    registry.register(ExcelRoleClassifierSkill())
    registry.register(CalculationPlannerSkill())
    registry.register(SpreadsheetCalculatorSkill())
    registry.register(TableMappingPreviewSkill())
    registry.register(TableFillerSkill())
    registry.register(TableDataTransferSkill())
    registry.register(FillValidatorSkill())
    return registry


__all__ = [
    "WorkflowSkillRegistry",
    "build_default_skill_registry",
]
