import json
from threading import Lock

from diagram_langgraph_pipeline.contracts import LLMResponse
from diagram_langgraph_pipeline.demo_data import demo_research_inputs, make_market_payload
from diagram_langgraph_pipeline.dependencies import AgentDependencies
from diagram_langgraph_pipeline.llm_orchestration import project_node_input
from diagram_langgraph_pipeline.profiles import apply_run_profile
from diagram_langgraph_pipeline.providers import InMemoryMarketDataProvider
from diagram_langgraph_pipeline.runner import run_research


class StructuredFakeLLM:
    def __init__(self):
        self.calls = []
        self.lock = Lock()

    def generate(self, messages, *, max_tokens=None, temperature=None):
        with self.lock:
            self.calls.append(
                {
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            )
        return LLMResponse(
            text=json.dumps(
                {
                    "summary": "模型建议买入，但只能作为非权威辅助意见。",
                    "findings": ["结构化发现"],
                    "conflicts": [],
                    "risks": ["模型风险"],
                    "missing_items": [],
                    "evidence_ids": [],
                    "confidence": 0.9,
                },
                ensure_ascii=False,
            ),
            model="deepseek-v4-flash-260425",
            provider="fake-d4f",
            request_id="fake-request",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )


def _state():
    return {
        "run_profile": "d4f_70d",
        "ticker": "STOCK",
        "company_name": "Test Company",
        "industry_name": "Test Industry",
        "as_of_date": "2026-07-31",
        "investment_horizon": "medium",
        "user_request": "完整研究",
        "benchmark_ticker": "BENCH",
        "sector_index_ticker": "SECTOR",
        "research_inputs": demo_research_inputs(),
        "retry_count": 0,
        "max_retries": 0,
    }


def test_d4f_70d_profile_defaults_do_not_override_callers():
    prepared = apply_run_profile({"run_profile": "d4f_70d", "news_limit": 20})

    assert prepared["daily_trading_days"] == 70
    assert prepared["intraday_interval"] == "60m"
    assert prepared["llm_scope"] == "all_nodes"
    assert prepared["llm_prompt_token_limit"] == 128_000
    assert prepared["news_limit"] == 20


def test_projector_removes_secrets_and_keeps_mandatory_daily_history():
    state = apply_run_profile(_state())
    payload = make_market_payload(20, 0.001)
    payload["technical_bars"] = list(payload["bars"][-251:])
    payload["api_key"] = "must-not-leak"
    state["stock_market_data"] = {
        "stock": payload,
        "benchmark": make_market_payload(100, 0.001),
        "sector": make_market_payload(50, 0.001),
    }

    projection = project_node_input(
        "stock_data_analysis", state, {"stock_market_data_analysis": {"score": 1}}
    )

    assert "must-not-leak" not in projection.canonical_json
    assert len(projection.payload["stock_market_data"]["stock"]["bars"]) == 70
    assert "technical_bars" not in projection.payload["stock_market_data"]["stock"]
    assert projection.estimated_tokens <= 128_000
    assert projection.manifest["candidate_char_count"] >= projection.manifest["projected_char_count"]


def test_projector_marks_oversized_mandatory_output_without_slicing_json():
    state = apply_run_profile(_state())
    state["llm_projection_target"] = 1_000
    state["llm_prompt_token_limit"] = 2_000

    projection = project_node_input(
        "report", state, {"final_markdown": "研究结论。" * 10_000}
    )

    assert projection.over_limit is True
    assert json.loads(projection.canonical_json)["deterministic_output"][
        "final_markdown"
    ].endswith("研究结论。")


def test_d4f_profile_invokes_all_23_nodes_and_keeps_decision_authoritative():
    payloads = {
        "STOCK": make_market_payload(20.0, 0.0010),
        "BENCH": make_market_payload(100.0, 0.0003),
        "SECTOR": make_market_payload(50.0, 0.0006),
    }
    llm = StructuredFakeLLM()

    result = run_research(
        _state(),
        AgentDependencies(
            market_data=InMemoryMarketDataProvider(payloads),
            llm=llm,
        ),
    )

    assert len(llm.calls) == 23
    assert len(result["llm_node_results"]) == 23
    assert all(not item["authoritative"] for item in result["llm_node_results"].values())
    assert result["decision_result"]["action_bias"] in {
        "buy",
        "hold",
        "watch",
        "reduce",
        "sell",
    }
    assert len(result["stock_market_data"]["stock"]["bars"]) == 70
    assert len(result["stock_market_data"]["stock"]["technical_bars"]) == 251
    assert result["stock_market_data_analysis"]["return_250d"] is not None
    assert result["stock_market_data_analysis"]["ma_status"]["ma250"]["value"] is not None
    assert "## 16. D4F 节点审计" in result["final_markdown"]
    assert all(
        item["projection_manifest"]["estimated_prompt_tokens"] <= 128_000
        for item in result["llm_node_results"].values()
    )
