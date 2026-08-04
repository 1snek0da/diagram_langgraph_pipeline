"""All-node D4F advisory orchestration with deterministic prompt projection."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from threading import BoundedSemaphore, Lock
from typing import Any, Iterable

from .dependencies import AgentDependencies


IDENTITY_FIELDS = (
    "run_id",
    "ticker",
    "company_name",
    "industry_name",
    "industry_code",
    "as_of_date",
    "investment_horizon",
    "user_request",
    "benchmark_ticker",
    "sector_index_ticker",
    "run_profile",
    "daily_trading_days",
    "technical_trading_days",
    "intraday_interval",
    "intraday_target_bars_per_day",
    "news_limit",
    "retry_count",
    "max_retries",
)

RESULT_FIELDS = (
    "planner_tasks",
    "industry_task_context",
    "stock_task_context",
    "market_task_context",
    "industry_report_result",
    "upstream_capex_result",
    "policy_result",
    "future_capex_forecast_result",
    "industry_valuation_result",
    "business_result",
    "profit_forecast_result",
    "marginal_change_result",
    "stock_market_data_analysis",
    "company_valuation_result",
    "stock_technical_result",
    "index_analysis_result",
    "sector_technical_result",
    "sentiment_result",
    "joined_research_result",
    "decision_result",
    "review_result",
)

DIRECT_PREDECESSORS: dict[str, tuple[str, ...]] = {
    "planner": (),
    "industry_entry": ("planner",),
    "stock_entry": ("planner",),
    "market_entry": ("planner",),
    "industry_report": ("industry_entry",),
    "upstream_capex": ("industry_report",),
    "policy": ("industry_report",),
    "future_capex_forecast": ("upstream_capex", "policy"),
    "industry_valuation": ("future_capex_forecast",),
    "stock_data_fetch": ("stock_entry",),
    "stock_data_analysis": ("stock_data_fetch",),
    "business": ("stock_entry",),
    "profit_forecast": ("business",),
    "marginal_change": ("business",),
    "company_valuation": ("profit_forecast", "marginal_change", "stock_data_analysis"),
    "stock_technical": ("stock_data_analysis",),
    "index_analysis": ("market_entry",),
    "sector_technical": ("market_entry",),
    "sentiment": ("market_entry",),
    "research_join": (
        "industry_valuation",
        "company_valuation",
        "stock_technical",
        "stock_data_analysis",
        "index_analysis",
        "sector_technical",
        "sentiment",
    ),
    "decision": ("research_join",),
    "review": ("decision",),
    "report": ("review",),
}

NODE_FIELDS: dict[str, tuple[str, ...]] = {
    "planner": ("research_inputs",),
    "industry_entry": ("planner_tasks", "research_inputs"),
    "stock_entry": ("planner_tasks", "research_inputs"),
    "market_entry": ("planner_tasks", "research_inputs"),
    "industry_report": ("industry_task_context", "research_inputs"),
    "upstream_capex": ("industry_report_result", "research_inputs"),
    "policy": ("industry_report_result", "research_inputs"),
    "future_capex_forecast": (
        "upstream_capex_result",
        "policy_result",
        "industry_report_result",
    ),
    "industry_valuation": (
        "future_capex_forecast_result",
        "industry_report_result",
        "research_inputs",
    ),
    "stock_data_fetch": ("stock_task_context", "stock_market_data"),
    "stock_data_analysis": ("stock_market_data",),
    "business": ("stock_task_context", "research_inputs"),
    "profit_forecast": ("business_result", "research_inputs"),
    "marginal_change": ("business_result", "research_inputs"),
    "company_valuation": (
        "profit_forecast_result",
        "marginal_change_result",
        "stock_market_data_analysis",
        "research_inputs",
    ),
    "stock_technical": ("stock_market_data", "stock_market_data_analysis"),
    "index_analysis": ("stock_market_data", "market_task_context"),
    "sector_technical": ("stock_market_data", "market_task_context"),
    "sentiment": ("research_inputs", "market_task_context"),
    "research_join": RESULT_FIELDS,
    "decision": RESULT_FIELDS + ("evidence_refs",),
    "review": RESULT_FIELDS + ("evidence_refs",),
    "report": RESULT_FIELDS + ("evidence_refs",),
}

CONTROL_NODES = {"planner", "industry_entry", "stock_entry", "market_entry"}
SYNTHESIS_NODES = {"research_join", "decision", "review", "report"}
STOCK_MARKET_NODES = {"stock_data_analysis", "stock_technical"}
INDEX_MARKET_NODES = {"index_analysis"}
SECTOR_MARKET_NODES = {"sector_technical"}

RESEARCH_TOPICS: dict[str, tuple[str, ...]] = {
    "industry_entry": ("industry_report", "upstream_capex", "policy", "industry_valuation"),
    "stock_entry": ("business", "profit_forecast", "marginal_change", "company_valuation"),
    "market_entry": ("sentiment",),
    "industry_report": ("industry_report",),
    "upstream_capex": ("upstream_capex",),
    "policy": ("policy",),
    "industry_valuation": ("industry_valuation",),
    "business": ("business",),
    "profit_forecast": ("profit_forecast",),
    "marginal_change": ("marginal_change",),
    "company_valuation": ("company_valuation",),
    "sentiment": ("sentiment",),
}

SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|password|passwd|secret|database_url|dsn|token)$",
    re.IGNORECASE,
)
PROMPT_OVERHEAD_TOKENS = 500


@dataclass(frozen=True)
class PromptProjection:
    payload: dict[str, Any]
    manifest: dict[str, Any]
    canonical_json: str
    estimated_tokens: int
    input_hash: str
    over_limit: bool


class LLMNodeOrchestrator:
    """Invoke an advisory model after each deterministic graph node."""

    def __init__(self, deps: AgentDependencies, max_concurrency: int = 3) -> None:
        self._deps = deps
        self._semaphore = BoundedSemaphore(max(1, max_concurrency))
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._cache_lock = Lock()

    def enabled(self, state: dict[str, Any]) -> bool:
        return self._deps.llm is not None and state.get("llm_scope") == "all_nodes"

    def analyze(
        self,
        node_name: str,
        state: dict[str, Any],
        deterministic_output: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.enabled(state):
            return None
        projection = project_node_input(node_name, state, deterministic_output)
        if projection.over_limit:
            result = _failure_result(
                "context_limit_exceeded",
                projection.manifest,
                projection.input_hash,
            )
            self._record(node_name, state, projection, result)
            return result

        cache_key = (node_name, projection.input_hash)
        with self._cache_lock:
            cached = self._cache.get(cache_key)
        if cached is not None:
            result = deepcopy(cached)
            result["cache_hit"] = True
            self._record(node_name, state, projection, result)
            return result

        budget = _output_budget(node_name)
        messages = _messages(node_name, projection.canonical_json, budget)
        try:
            with self._semaphore:
                response = self._deps.llm.generate(
                    messages,
                    max_tokens=budget,
                    temperature=0.1,
                )
            parsed = _parse_json_object(response.text)
            repaired = False
            if parsed is None:
                repaired = True
                repair_messages = messages + [
                    {"role": "assistant", "content": response.text},
                    {
                        "role": "user",
                        "content": (
                            "上一个响应不是有效 JSON。仅重新输出符合既定 schema 的 JSON，"
                            "不得增加输入中不存在的事实。summary 不超过 80 字；每个数组最多 2 项，"
                            "每项不超过 60 字；evidence_ids 最多 5 项。不要解释。"
                        ),
                    },
                ]
                with self._semaphore:
                    response = self._deps.llm.generate(
                        repair_messages,
                        max_tokens=budget,
                        temperature=0.0,
                    )
                parsed = _parse_json_object(response.text)
            if parsed is None:
                result = _failure_result(
                    "invalid_json", projection.manifest, projection.input_hash
                )
                result.update(_response_metadata(response))
            else:
                result = _normalized_result(
                    parsed,
                    response,
                    projection,
                    repaired=repaired,
                )
        except Exception as exc:  # model failures never override deterministic logic
            result = _failure_result(
                type(exc).__name__, projection.manifest, projection.input_hash
            )
            result["error_message"] = str(exc)[:500]

        with self._cache_lock:
            self._cache[cache_key] = deepcopy(result)
        self._record(node_name, state, projection, result)
        return result

    def _record(
        self,
        node_name: str,
        state: dict[str, Any],
        projection: PromptProjection,
        result: dict[str, Any],
    ) -> None:
        recorder = getattr(self._deps.repository, "record_llm_invocation", None)
        if callable(recorder):
            recorder(
                str(state.get("run_id", "")),
                node_name,
                {
                    "status": result.get("status", "failed"),
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                    "request_id": result.get("request_id"),
                    "input_hash": projection.input_hash,
                    "candidate_char_count": projection.manifest["candidate_char_count"],
                    "projected_char_count": projection.manifest["projected_char_count"],
                    "estimated_prompt_tokens": projection.estimated_tokens,
                    "usage": result.get("usage", {}),
                    "projection_manifest": projection.manifest,
                    "error_type": result.get("error_type"),
                    "error_message": result.get("error_message"),
                    "cache_hit": result.get("cache_hit", False),
                },
            )


def project_node_input(
    node_name: str,
    state: dict[str, Any],
    deterministic_output: dict[str, Any],
) -> PromptProjection:
    """Build a stable, task-relevant prompt without slicing serialized JSON."""

    target = max(1_000, int(state.get("llm_projection_target", 115_000)))
    hard_limit = max(target, int(state.get("llm_prompt_token_limit", 128_000)))
    candidate: dict[str, Any] = {
        key: deepcopy(state[key]) for key in IDENTITY_FIELDS if key in state
    }
    included_paths = list(candidate)
    for key in NODE_FIELDS.get(node_name, RESULT_FIELDS):
        if key in state and key not in candidate:
            candidate[key] = deepcopy(state[key])
            included_paths.append(key)
    for key in ("missing_items", "risk_points"):
        if key in state:
            candidate[key] = deepcopy(state[key])
            included_paths.append(key)

    candidate["predecessor_llm_analysis"] = _project_llm_results(
        node_name, state.get("llm_node_results", {})
    )
    candidate["deterministic_output"] = deepcopy(deterministic_output)
    candidate = _remove_sensitive(candidate)
    candidate_json = _canonical(candidate)

    manifest: dict[str, Any] = {
        "strategy": "node_relevant",
        "included_paths": sorted(set(included_paths)),
        "omitted_paths": sorted(set(state) - set(included_paths) - {"llm_node_results"}),
        "candidate_char_count": len(candidate_json),
        "projected_char_count": 0,
        "estimated_prompt_tokens": 0,
        "target_tokens": target,
        "hard_limit_tokens": hard_limit,
        "reductions": [],
    }
    candidate["deterministic_output"] = _project_current_output(
        node_name, candidate["deterministic_output"], manifest=manifest
    )

    if "research_inputs" in candidate:
        candidate["research_inputs"] = _select_research_inputs(
            node_name, candidate["research_inputs"], manifest
        )
        candidate["research_inputs"] = _project_research_inputs(
            candidate["research_inputs"], 1200, manifest
        )
    if "stock_market_data" in candidate:
        candidate["stock_market_data"] = _project_market_data(
            node_name,
            candidate["stock_market_data"],
            int(state.get("intraday_recent_full_days", 20)),
            manifest,
        )
    candidate = _dedupe_evidence(candidate, manifest)
    projected_json = _canonical(candidate)
    estimated = _prompt_estimate(projected_json)

    if estimated > target:
        _compact_non_direct_llm(candidate, node_name, manifest)
        _shrink_source_text(candidate, 2_000, manifest)
        _shrink_news(candidate, 600, manifest)
        projected_json = _canonical(candidate)
        estimated = _prompt_estimate(projected_json)
    if estimated > target:
        _reduce_old_intraday(candidate, manifest)
        projected_json = _canonical(candidate)
        estimated = _prompt_estimate(projected_json)
    if estimated > target:
        _drop_low_priority_optional(candidate, manifest, target)
        projected_json = _canonical(candidate)
        estimated = _prompt_estimate(projected_json)

    manifest["projected_char_count"] = len(projected_json)
    manifest["estimated_prompt_tokens"] = estimated
    digest = sha256(f"{node_name}\n{projected_json}".encode("utf-8")).hexdigest()
    return PromptProjection(
        payload=candidate,
        manifest=manifest,
        canonical_json=projected_json,
        estimated_tokens=estimated,
        input_hash=digest,
        over_limit=estimated > hard_limit,
    )


def estimate_tokens(text: str) -> int:
    """Conservative tokenizer-independent estimate for mixed CJK/JSON input."""

    cjk = sum(1 for char in text if "\u2e80" <= char <= "\u9fff")
    non_cjk = len(text) - cjk
    return int(math.ceil((cjk + non_cjk / 3.0) * 1.20))


def _prompt_estimate(payload_json: str) -> int:
    return estimate_tokens(payload_json) + PROMPT_OVERHEAD_TOKENS


def _messages(
    node_name: str, payload_json: str, output_budget: int
) -> list[dict[str, str]]:
    schema = (
        '{"summary":"string","findings":["string"],"conflicts":["string"],'
        '"risks":["string"],"missing_items":["string"],'
        '"evidence_ids":["string"],"confidence":0.0}'
    )
    return [
        {
            "role": "system",
            "content": (
                f"你是股票研究流程中的 {node_name} 辅助分析节点。只使用输入中的事实，"
                "不得引入新事实，不得修改确定性指标、估值、决策、置信度或 Review 路由，"
                "不得给出自动下单指令。输出且仅输出有效 JSON，不要输出思考过程、Markdown 或解释。"
                "summary 不超过 80 字；findings、conflicts、risks、missing_items 每个最多 2 项，"
                "每项不超过 60 字；evidence_ids 最多 5 项。没有内容时输出空数组。"
                f"总输出必须显著少于 {output_budget} Token。schema 为：" + schema
            ),
        },
        {"role": "user", "content": payload_json},
    ]


def _output_budget(node_name: str) -> int:
    if node_name in CONTROL_NODES or node_name == "stock_data_fetch":
        return 300
    if node_name in {"research_join", "decision", "review"}:
        return 800
    if node_name == "report":
        return 1200
    return 600


def _parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    try:
        value = json.loads(cleaned)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _normalized_result(
    parsed: dict[str, Any],
    response: Any,
    projection: PromptProjection,
    *,
    repaired: bool,
) -> dict[str, Any]:
    def strings(key: str) -> list[str]:
        value = parsed.get(key, [])
        if not isinstance(value, list):
            value = [value]
        return [str(item) for item in value if item not in (None, "")]

    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    return {
        "status": "completed",
        "summary": str(parsed.get("summary", "")),
        "findings": strings("findings"),
        "conflicts": strings("conflicts"),
        "risks": strings("risks"),
        "missing_items": strings("missing_items"),
        "evidence_ids": strings("evidence_ids"),
        "confidence": confidence,
        **_response_metadata(response),
        "projection_manifest": projection.manifest,
        "input_hash": projection.input_hash,
        "json_repaired": repaired,
        "authoritative": False,
    }


def _response_metadata(response: Any) -> dict[str, Any]:
    return {
        "provider": response.provider,
        "model": response.model,
        "request_id": response.request_id,
        "finish_reason": response.finish_reason,
        "usage": response.usage,
    }


def _failure_result(
    error_type: str, manifest: dict[str, Any], input_hash: str
) -> dict[str, Any]:
    return {
        "status": "failed",
        "error_type": error_type,
        "error_message": None,
        "projection_manifest": manifest,
        "input_hash": input_hash,
        "usage": {},
        "authoritative": False,
    }


def _project_llm_results(node_name: str, results: Any) -> dict[str, Any]:
    if not isinstance(results, dict):
        return {}
    direct = set(DIRECT_PREDECESSORS.get(node_name, ()))
    if node_name in SYNTHESIS_NODES:
        return deepcopy(results)
    return {key: deepcopy(value) for key, value in results.items() if key in direct}


def _project_research_inputs(
    value: Any, summary_limit: int, manifest: dict[str, Any]
) -> Any:
    projected = deepcopy(value)
    _shrink_news(projected, summary_limit, manifest)
    _shrink_source_text(projected, 2_000, manifest)
    return projected


def _select_research_inputs(
    node_name: str, value: Any, manifest: dict[str, Any]
) -> Any:
    if not isinstance(value, dict):
        return value
    if node_name == "planner":
        result = {key: _research_catalog(item) for key, item in value.items()}
    elif node_name in CONTROL_NODES:
        allowed = RESEARCH_TOPICS.get(node_name, ())
        result = {
            key: _research_catalog(value[key]) for key in allowed if key in value
        }
    else:
        allowed = RESEARCH_TOPICS.get(node_name)
        result = (
            {key: deepcopy(value[key]) for key in allowed if key in value}
            if allowed is not None
            else deepcopy(value)
        )
    if len(result) != len(value) or node_name in CONTROL_NODES:
        manifest["reductions"].append(
            {
                "kind": "research_topic_projection",
                "from": len(value),
                "to": len(result),
            }
        )
    return result


def _research_catalog(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"available": value not in (None, "", [], {})}
    evidence = value.get("evidence", [])
    facts = value.get("metric_facts", [])
    return {
        "available": any(item not in (None, "", [], {}) for item in value.values()),
        "fields": sorted(value),
        "evidence_count": len(evidence) if isinstance(evidence, list) else int(bool(evidence)),
        "metric_fact_count": len(facts) if isinstance(facts, list) else int(bool(facts)),
        "source_coverage": value.get("source_coverage"),
        "source_warnings": value.get("source_warnings", []),
        "source_errors": value.get("source_errors", []),
    }


def _project_market_data(
    node_name: str,
    market: Any,
    recent_full_days: int,
    manifest: dict[str, Any],
) -> Any:
    if not isinstance(market, dict):
        return market
    result = deepcopy(market)
    targets = {
        "stock": node_name in STOCK_MARKET_NODES,
        "benchmark": node_name in INDEX_MARKET_NODES,
        "sector": node_name in SECTOR_MARKET_NODES,
    }
    for key in ("stock", "benchmark", "sector"):
        payload = result.get(key)
        if not isinstance(payload, dict):
            continue
        bars = payload.get("bars")
        if isinstance(bars, list):
            payload["bars"] = bars[-70:]
        technical_bars = payload.pop("technical_bars", None)
        if isinstance(technical_bars, list):
            manifest["reductions"].append(
                {
                    "path": f"stock_market_data.{key}.technical_bars",
                    "from": len(technical_bars),
                    "to": 0,
                    "reason": "long_history_replaced_by_deterministic_metrics",
                }
            )
        intraday = payload.get("minute_bars")
        if not isinstance(intraday, list):
            continue
        original = len(intraday)
        if node_name == "stock_data_fetch":
            payload["minute_bars"] = _edge_sample(intraday, 12)
        elif node_name in SYNTHESIS_NODES:
            payload["minute_bars"] = []
        elif targets[key]:
            payload["minute_bars"] = intraday
        else:
            payload["minute_bars"] = _last_trading_days(intraday, recent_full_days)
        kept = len(payload["minute_bars"])
        if kept != original:
            manifest["reductions"].append(
                {"path": f"stock_market_data.{key}.minute_bars", "from": original, "to": kept}
            )
    return result


def _project_current_output(
    node_name: str,
    output: dict[str, Any],
    manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    projected = deepcopy(output)
    if node_name != "stock_data_fetch":
        return projected
    market = projected.get("stock_market_data")
    if not isinstance(market, dict):
        return projected
    local_manifest = manifest if manifest is not None else {"reductions": []}
    projected["stock_market_data"] = _project_market_data(
        "stock_data_fetch", market, 20, local_manifest
    )
    return projected


def _remove_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _remove_sensitive(item)
            for key, item in value.items()
            if not SENSITIVE_KEY.search(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [_remove_sensitive(item) for item in value]
    return _jsonable(value)


def _dedupe_evidence(value: Any, manifest: dict[str, Any]) -> Any:
    seen: set[str] = set()
    removed = 0

    def visit(item: Any) -> Any:
        nonlocal removed
        if isinstance(item, dict):
            identifier = item.get("evidence_id") or item.get("source_id")
            if identifier and ("claim_text" in item or "evidence_type" in item):
                marker = str(identifier)
                if marker in seen:
                    removed += 1
                    return {
                        "evidence_id": item.get("evidence_id"),
                        "source_id": item.get("source_id"),
                        "duplicate": True,
                    }
                seen.add(marker)
            return {str(key): visit(child) for key, child in item.items()}
        if isinstance(item, list):
            return [visit(child) for child in item]
        return item

    result = visit(value)
    if removed:
        manifest["reductions"].append({"kind": "duplicate_evidence", "count": removed})
    return result


def _compact_non_direct_llm(
    payload: dict[str, Any], node_name: str, manifest: dict[str, Any]
) -> None:
    results = payload.get("predecessor_llm_analysis")
    if not isinstance(results, dict):
        return
    direct = set(DIRECT_PREDECESSORS.get(node_name, ()))
    changed = 0
    for key, item in list(results.items()):
        if key in direct or not isinstance(item, dict):
            continue
        results[key] = {
            field: item.get(field)
            for field in ("status", "summary", "conflicts", "risks", "evidence_ids", "confidence")
            if field in item
        }
        changed += 1
    if changed:
        manifest["reductions"].append({"kind": "compact_non_direct_llm", "count": changed})


def _shrink_news(value: Any, limit: int, manifest: dict[str, Any]) -> None:
    changed = 0
    for item in _walk_dicts(value):
        if "summary" in item and (
            "published_at" in item or "publisher" in item or item.get("evidence_type") == "news"
        ):
            text = item.get("summary")
            if isinstance(text, str) and len(text) > limit:
                item["summary"] = _paragraph_cut(text, limit)
                changed += 1
        quote = item.get("quote_text")
        if item.get("evidence_type") == "news" and isinstance(quote, str) and len(quote) > limit:
            item["quote_text"] = _paragraph_cut(quote, limit)
            changed += 1
    if changed:
        manifest["reductions"].append({"kind": "news_summary", "limit_chars": limit, "count": changed})


def _shrink_source_text(value: Any, limit: int, manifest: dict[str, Any]) -> None:
    changed = 0
    for item in _walk_dicts(value):
        for key in ("text", "content", "body", "excerpt"):
            text = item.get(key)
            if isinstance(text, str) and len(text) > limit:
                item[key] = _paragraph_cut(text, limit)
                changed += 1
    if changed:
        manifest["reductions"].append({"kind": "source_text", "limit_chars": limit, "count": changed})


def _reduce_old_intraday(payload: dict[str, Any], manifest: dict[str, Any]) -> None:
    market = payload.get("stock_market_data")
    if not isinstance(market, dict):
        return
    for key in ("stock", "benchmark", "sector"):
        item = market.get(key)
        if not isinstance(item, dict) or not isinstance(item.get("minute_bars"), list):
            continue
        bars = item["minute_bars"]
        reduced = _three_per_day(bars)
        if len(reduced) < len(bars):
            item["minute_bars"] = reduced
            manifest["reductions"].append(
                {"path": f"stock_market_data.{key}.minute_bars", "from": len(bars), "to": len(reduced)}
            )


def _drop_low_priority_optional(
    payload: dict[str, Any], manifest: dict[str, Any], target: int
) -> None:
    for key in ("research_inputs", "predecessor_llm_analysis", "stock_market_data"):
        if _prompt_estimate(_canonical(payload)) <= target:
            return
        if key not in payload:
            continue
        if key == "research_inputs":
            _remove_unreferenced_quotes(payload[key])
            manifest["reductions"].append({"kind": "remove_unreferenced_quotes"})
        elif key == "predecessor_llm_analysis":
            for item in payload[key].values():
                if isinstance(item, dict):
                    item.pop("findings", None)
            manifest["reductions"].append({"kind": "remove_nonessential_llm_findings"})
        else:
            _reduce_old_intraday(payload, manifest)


def _remove_unreferenced_quotes(value: Any) -> None:
    for item in _walk_dicts(value):
        if item.get("evidence_type") == "news":
            item.pop("quote_text", None)
            item.pop("summary", None)


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _edge_sample(items: list[Any], count: int) -> list[Any]:
    if len(items) <= count:
        return items
    half = max(1, count // 2)
    return items[:half] + items[-half:]


def _last_trading_days(items: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    dates = []
    for item in reversed(items):
        day = str(item.get("trade_date", ""))[:10]
        if day and day not in dates:
            dates.append(day)
        if len(dates) >= days:
            break
    allowed = set(dates)
    return [item for item in items if str(item.get("trade_date", ""))[:10] in allowed]


def _three_per_day(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get("trade_date", ""))[:10], []).append(item)
    result: list[dict[str, Any]] = []
    for group in grouped.values():
        if len(group) <= 3:
            result.extend(group)
        else:
            result.extend((group[0], group[len(group) // 2], group[-1]))
    return result


def _paragraph_cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    prefix = text[:limit]
    boundary = max(prefix.rfind("\n"), prefix.rfind("。"), prefix.rfind(". "))
    return prefix[: boundary + 1] if boundary >= limit // 2 else prefix


def _canonical(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
