import json

import httpx

from diagram_langgraph_pipeline.agents import report_agent
from diagram_langgraph_pipeline.contracts import LLMResponse
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider
from diagram_langgraph_pipeline.providers.volcengine_llm import (
    VolcengineChatClient,
    VolcengineLLMConfig,
)


def test_volcengine_client_uses_openai_compatible_chat_endpoint():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"x-request-id": "req-test"},
            json={
                "id": "chat-test",
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "辅助解读"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            },
        )

    transport = httpx.MockTransport(handler)
    client = VolcengineChatClient(
        VolcengineLLMConfig(
            api_key="test-secret",
            base_url="https://relay.example.com/v1",
            model="deepseek-v4-flash",
            disable_thinking=True,
            json_mode=True,
        ),
        client=httpx.Client(transport=transport),
    )

    result = client.generate([{"role": "user", "content": "test"}])

    assert captured["url"] == "https://relay.example.com/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-secret"
    assert captured["body"]["model"] == "deepseek-v4-flash"
    assert captured["body"]["thinking"] == {"type": "disabled"}
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert result.text == "辅助解读"
    assert result.request_id == "req-test"


class _FakeLLM:
    def generate(self, messages, *, max_tokens=None, temperature=None):
        assert "不得修改决策倾向" in messages[0]["content"]
        return LLMResponse(
            text="模型声称应该买入，但此文本只能作为辅助解读。",
            model="deepseek-v4-flash",
            provider="test-relay",
            request_id="req-1",
        )


def test_report_keeps_rule_decision_authoritative_when_llm_is_enabled():
    deps = AgentDependencies(
        market_data=InMemoryMarketDataProvider({}),
        llm=_FakeLLM(),
    )
    state = {
        "run_id": "run-1",
        "ticker": "TEST",
        "company_name": "Test Company",
        "industry_name": "Test Industry",
        "as_of_date": "2026-07-31",
        "decision_result": {"action_bias": "watch", "score": 0},
        "review_result": {"passed": False},
        "missing_items": ["缺少基本面证据"],
    }

    output = report_agent.run(state, deps)

    assert output["llm_advisory_result"]["authoritative"] is False
    assert output["llm_advisory_result"]["model"] == "deepseek-v4-flash"
    assert "**决策倾向**：watch" in output["final_markdown"]
    assert "仅辅助解读；不参与规则决策与 Review" in output["final_markdown"]
