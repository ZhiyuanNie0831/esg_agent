import unittest

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


class ApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health_endpoint_reports_workflow_service_state(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "agent_v0")
        self.assertEqual(payload["provider"], settings.model_api_provider)
        self.assertEqual(payload["providerLabel"], settings.model_api_provider_label)
        self.assertEqual(payload["protocol"], settings.model_api_protocol)
        self.assertEqual(payload["apiConfigured"], bool(settings.model_api_key))
        self.assertEqual(payload["apiBaseUrl"], settings.model_api_base_url)
        self.assertEqual(payload["model"], settings.model_api_model)
        self.assertEqual(payload["workflowMode"], "agent_orchestrated_with_local_skills")
        self.assertEqual(payload["agentEnabled"], bool(settings.model_api_key) and settings.model_api_agent_enabled)
        self.assertEqual(payload["ocrEnabled"], bool(settings.model_api_ocr_key) and settings.model_api_ocr_enabled)
        self.assertEqual(payload["ocrProvider"], settings.model_api_ocr_provider)
        self.assertEqual(payload["ocrProviderLabel"], settings.model_api_ocr_provider_label)
        self.assertEqual(payload["ocrProtocol"], settings.model_api_ocr_protocol)
        self.assertEqual(payload["ocrApiConfigured"], bool(settings.model_api_ocr_key))
        self.assertEqual(payload["ocrApiBaseUrl"], settings.model_api_ocr_base_url)
        self.assertEqual(payload["ocrModel"], settings.model_api_ocr_model)
        self.assertEqual(payload["ocrPdfMode"], settings.model_api_ocr_pdf_mode)
        self.assertEqual(payload["confirmationMode"], "risk_based")

    def test_sql_and_demo_routes_are_not_exposed(self) -> None:
        self.assertEqual(self.client.get("/api/demo/schema").status_code, 404)
        self.assertEqual(self.client.post("/api/nl2sql/generate", json={}).status_code, 404)

    def test_index_uses_fixed_agent_mode_and_local_fallback_toggle(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('id="agentMode"', response.text)
        self.assertNotIn("Agent 模式", response.text)
        self.assertIn('id="localFallbackEnabled"', response.text)
        self.assertIn("允许本地回退", response.text)

    def test_index_contains_downloads_panel(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="downloads-output"', response.text)
        self.assertIn("导出文件", response.text)

    def test_index_contains_confirmation_panel(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="confirmation-output"', response.text)
        self.assertIn("人工确认", response.text)
        self.assertIn("需要复核的计划、风险步骤或表格映射", response.text)
        self.assertIn('id="manualConfirm" name="manualConfirm" type="checkbox" />', response.text)

    def test_confirmation_panel_contains_confirm_action_button(self) -> None:
        panel_response = self.client.get("/static/js/views/confirmation-panel.js")
        app_response = self.client.get("/static/js/app.js")

        self.assertEqual(panel_response.status_code, 200)
        self.assertEqual(app_response.status_code, 200)
        self.assertIn('data-confirmation-action="confirm_execute"', panel_response.text)
        self.assertIn("确认并继续执行", panel_response.text)
        self.assertIn("handleConfirmationPanelClick", app_response.text)

    def test_workflow_bundle_uses_generic_confirmation_copy(self) -> None:
        response = self.client.get("/workflow-bundle")

        self.assertEqual(response.status_code, 200)
        self.assertIn("高影响步骤确认", response.text)
        self.assertNotIn("右侧“人工确认”面板已经展示了自动识别的填表位置", response.text)


if __name__ == "__main__":
    unittest.main()
