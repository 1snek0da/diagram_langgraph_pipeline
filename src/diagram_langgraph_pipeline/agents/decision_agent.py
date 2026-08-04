"""Rule-backed buy/hold/watch/reduce/sell decision node."""

from __future__ import annotations

from typing import Any

from ..dependencies import AgentDependencies


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []
    conflicts: list[str] = []
    industry = state.get("future_capex_forecast_result", {})
    forecast = state.get("profit_forecast_result", {})
    marginal = state.get("marginal_change_result", {})
    market_data = state.get("stock_market_data_analysis", {})
    technical = state.get("stock_technical_result", {})
    company_valuation = state.get("company_valuation_result", {})
    index = state.get("index_analysis_result", {})
    sentiment = state.get("sentiment_result", {})

    if industry.get("trend") == "positive":
        score += 2
        reasons.append("行业资本开支、政策与技术信号整体偏正面")
    elif industry.get("trend") == "negative":
        score -= 2
        reasons.append("行业综合趋势偏弱")

    if forecast.get("revision_direction") == "up":
        score += 2
        reasons.append("盈利预测上修")
    elif forecast.get("revision_direction") == "down":
        score -= 2
        reasons.append("盈利预测下修")

    if marginal.get("direction") == "positive":
        score += 1
        reasons.append("出现正向边际变化")
    elif marginal.get("direction") == "negative":
        score -= 1
        reasons.append("出现负向边际变化")

    trend = technical.get("trend")
    if trend == "up":
        score += 1
        reasons.append("股价位于主要均线之上")
    elif trend == "down":
        score -= 1
        reasons.append("股价位于主要均线之下")

    pe_percentile = (
        market_data.get("valuation_percentile", {}).get("pe_ttm", {}).get("percentile")
    )
    high_valuation = pe_percentile is not None and pe_percentile >= 0.8
    crowded = sentiment.get("crowding_risk") == "high"
    high_position = bool(technical.get("high_position_risk"))
    if high_valuation:
        score -= 1
        conflicts.append("趋势可能较强，但 PE 位于历史高分位")
    if crowded:
        score -= 1
        conflicts.append("情绪拥挤降低追买性价比")
    if high_position:
        score -= 1
        conflicts.append("价格显著偏离短期均线")
    if index.get("risk_preference") == "risk_off":
        score -= 2
        conflicts.append("大盘处于 risk-off 环境，个股正面信号需折价")

    valuation_signal = company_valuation.get("investment_signal", {}).get("signal")
    if valuation_signal == "strong_buy":
        score += 2
        reasons.append("逐年调整后盈利与PE测算显示较大的未来市值空间")
    elif valuation_signal == "buy":
        score += 1
        reasons.append("逐年估值空间达到文档定义的买入阈值")
    elif valuation_signal == "sell":
        score -= 2
        conflicts.append("当前市值高于2027年合理市值基准")

    technical_signal = technical.get("composite_scoring", {}).get("signal_strength")
    if technical_signal == "strong":
        score += 1
        reasons.append("趋势与突破形态综合评分为强信号")
    elif technical_signal == "avoid_entry":
        score -= 1
        conflicts.append("趋势与形态综合评分不满足介入条件")

    missing = state.get("missing_items", [])
    coverage = market_data.get("data_coverage", {}).get("coverage_ratio", 0.0)
    evidence_count = len(state.get("evidence_refs", []))
    confidence = min(0.95, 0.35 + min(evidence_count, 6) * 0.07 + coverage * 0.18)
    if missing:
        confidence -= min(0.3, len(missing) * 0.05)
    confidence = round(max(0.1, confidence), 4)

    if score >= 4:
        action = "buy"
    elif score >= 1:
        action = "hold"
    elif score >= -1:
        action = "watch"
    elif score >= -3:
        action = "reduce"
    else:
        action = "sell"

    if (missing or coverage < 0.8 or evidence_count < 3) and action in {"buy", "sell"}:
        action = "watch" if score >= 0 else "reduce"
        conflicts.append("证据或行情覆盖不足，禁止输出高置信度极端结论")
        confidence = min(confidence, 0.55)
    if action == "buy" and (high_valuation or crowded or high_position):
        action = "hold"
        conflicts.append("基本面与高估值/高位技术形态冲突，避免直接追买")

    support = technical.get("support_price")
    resistance = technical.get("resistance_price")
    return {
        "decision_result": {
            "action_bias": action,
            "score": score,
            "document_valuation_signal": valuation_signal,
            "technical_composite_signal": technical_signal,
            "conviction": (
                "high"
                if confidence >= 0.75
                else "medium" if confidence >= 0.5 else "low"
            ),
            "confidence_score": confidence,
            "buy_zone": {"reference_support": support},
            "sell_zone": {"reference_resistance": resistance},
            "invalid_condition": "行业趋势、盈利预测或关键价格趋势发生反转",
            "supporting_points": reasons,
            "conflict_points": conflicts,
            "risk_points": state.get("risk_points", []),
        }
    }
