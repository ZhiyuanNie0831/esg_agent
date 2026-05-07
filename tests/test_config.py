import os
import unittest
from unittest.mock import patch

from app.config import get_settings


class SettingsProviderInferenceTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    @patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_MODEL": "gpt-5.4",
        },
        clear=True,
    )
    def test_openai_env_defaults_to_openai_provider(self) -> None:
        get_settings.cache_clear()

        settings = get_settings()

        self.assertEqual(settings.model_api_provider, "openai")
        self.assertEqual(settings.model_api_provider_label, "OpenAI")
        self.assertEqual(settings.model_api_protocol, "responses")
        self.assertEqual(settings.model_api_base_url, "https://api.openai.com/v1")
        self.assertEqual(settings.model_api_model, "gpt-5.4")

    @patch.dict(
        os.environ,
        {
            "MODEL_API_KEY": "test-key",
            "MODEL_API_MODEL": "qwen-plus",
        },
        clear=True,
    )
    def test_model_api_env_keeps_dashscope_default(self) -> None:
        get_settings.cache_clear()

        settings = get_settings()

        self.assertEqual(settings.model_api_provider, "dashscope")
        self.assertEqual(settings.model_api_provider_label, "阿里云百炼")
        self.assertEqual(settings.model_api_base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertEqual(settings.model_api_model, "qwen-plus")
        self.assertEqual(settings.model_api_review_provider, "deepseek")
        self.assertIsNone(settings.model_api_review_key)
        self.assertEqual(settings.model_api_review_model, "deepseek-chat")

    @patch.dict(
        os.environ,
        {
            "MODEL_API_PROVIDER": "deepseek",
            "OPENAI_API_KEY": "test-key",
            "OPENAI_MODEL": "gpt-5.4",
        },
        clear=True,
    )
    def test_explicit_model_api_provider_wins(self) -> None:
        get_settings.cache_clear()

        settings = get_settings()

        self.assertEqual(settings.model_api_provider, "deepseek")
        self.assertEqual(settings.model_api_provider_label, "DeepSeek")
        self.assertEqual(settings.model_api_base_url, "https://api.deepseek.com")

    @patch.dict(
        os.environ,
        {
            "MODEL_API_REVIEW_PROVIDER": "zhipu",
            "MODEL_API_REVIEW_KEY": "review-key",
            "MODEL_API_REVIEW_MODEL": "glm-4.5",
        },
        clear=True,
    )
    def test_review_api_has_separate_provider_and_key(self) -> None:
        get_settings.cache_clear()

        settings = get_settings()

        self.assertEqual(settings.model_api_review_provider, "zhipu")
        self.assertEqual(settings.model_api_review_provider_label, "智谱AI")
        self.assertEqual(settings.model_api_review_key, "review-key")
        self.assertEqual(settings.model_api_review_model, "glm-4.5")
        self.assertTrue(settings.model_api_review_enabled)

    @patch.dict(
        os.environ,
        {
            "OPENAI_REVIEW_API_KEY": "review-key",
            "OPENAI_REVIEW_MODEL": "gpt-5.4-mini",
        },
        clear=True,
    )
    def test_openai_review_aliases_enable_openai_review_api(self) -> None:
        get_settings.cache_clear()

        settings = get_settings()

        self.assertEqual(settings.model_api_review_provider, "openai")
        self.assertEqual(settings.model_api_review_provider_label, "OpenAI")
        self.assertEqual(settings.model_api_review_protocol, "responses")
        self.assertEqual(settings.model_api_review_key, "review-key")
        self.assertEqual(settings.model_api_review_base_url, "https://api.openai.com/v1")
        self.assertEqual(settings.model_api_review_model, "gpt-5.4-mini")
        self.assertTrue(settings.model_api_review_enabled)


if __name__ == "__main__":
    unittest.main()
