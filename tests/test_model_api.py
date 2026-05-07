import unittest
from unittest.mock import MagicMock, patch

from app.services.model_api import ModelApiConfig, build_model_api_gateway


class ModelApiGatewayTests(unittest.TestCase):
    @patch("app.services.model_api.httpx.Client")
    def test_chat_completions_gateway_posts_compatible_payload(self, client_cls) -> None:
        http_client = MagicMock()
        http_response = MagicMock()
        http_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "测试成功",
                    }
                }
            ]
        }
        http_client.post.return_value = http_response
        client_cls.return_value = http_client

        gateway = build_model_api_gateway(
            ModelApiConfig(
                provider="deepseek",
                api_key="test-key",
                base_url="https://api.deepseek.com",
                timeout_seconds=30,
            )
        )
        result = gateway.request_text(
            model="deepseek-chat",
            instructions="你是助手",
            input_payload="你好",
            max_output_tokens=256,
            reasoning_effort="high",
        )

        self.assertEqual(result, "测试成功")
        _, kwargs = http_client.post.call_args
        self.assertEqual(http_client.post.call_args.args[0], "chat/completions")
        self.assertEqual(kwargs["json"]["model"], "deepseek-chat")
        self.assertEqual(kwargs["json"]["messages"][0]["role"], "system")
        self.assertEqual(kwargs["json"]["messages"][1]["role"], "user")
        self.assertEqual(kwargs["json"]["reasoning_effort"], "high")

    @patch("app.services.model_api.httpx.Client")
    def test_responses_gateway_posts_current_payload_shape(self, client_cls) -> None:
        http_client = MagicMock()
        http_response = MagicMock()
        http_response.json.return_value = {
            "output_text": "结构化结果",
        }
        http_client.post.return_value = http_response
        client_cls.return_value = http_client

        gateway = build_model_api_gateway(
            ModelApiConfig(
                provider="dashscope",
                api_key="test-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                timeout_seconds=30,
            )
        )
        result = gateway.request_text(
            model="qwen-plus",
            instructions="你是助手",
            input_payload=[{"role": "user", "content": [{"type": "input_text", "text": "你好"}]}],
            max_output_tokens=256,
            reasoning_effort="medium",
        )

        self.assertEqual(result, "结构化结果")
        _, kwargs = http_client.post.call_args
        self.assertEqual(http_client.post.call_args.args[0], "responses")
        self.assertEqual(kwargs["json"]["model"], "qwen-plus")
        self.assertEqual(kwargs["json"]["instructions"], "你是助手")
        self.assertEqual(kwargs["json"]["reasoning"], {"effort": "medium"})
        self.assertEqual(kwargs["json"]["input"][0]["role"], "user")

    @patch("app.services.model_api.httpx.Client")
    def test_responses_gateway_retries_without_unsupported_temperature(self, client_cls) -> None:
        http_client = MagicMock()
        rejected_response = MagicMock()
        rejected_response.status_code = 400
        rejected_response.json.return_value = {
            "error": {
                "message": "Unsupported parameter: 'temperature' is not supported with this model.",
                "param": "temperature",
            }
        }
        accepted_response = MagicMock()
        accepted_response.status_code = 200
        accepted_response.json.return_value = {"output_text": "OK"}
        http_client.post.side_effect = [rejected_response, accepted_response]
        client_cls.return_value = http_client

        gateway = build_model_api_gateway(
            ModelApiConfig(
                provider="openai",
                api_key="test-key",
                base_url="https://api.openai.com/v1",
                timeout_seconds=30,
                protocol="responses",
            )
        )
        result = gateway.request_text(
            model="gpt-5.4-mini",
            instructions="你是助手",
            input_payload="你好",
            max_output_tokens=64,
            temperature=0,
        )

        self.assertEqual(result, "OK")
        self.assertEqual(http_client.post.call_count, 2)
        first_payload = http_client.post.call_args_list[0].kwargs["json"]
        second_payload = http_client.post.call_args_list[1].kwargs["json"]
        self.assertEqual(first_payload["temperature"], 0)
        self.assertNotIn("temperature", second_payload)


if __name__ == "__main__":
    unittest.main()
