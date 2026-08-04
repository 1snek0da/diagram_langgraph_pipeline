"""Named execution profiles for the research pipeline."""

from __future__ import annotations

from typing import Any, Mapping


D4F_70D_PROFILE: dict[str, Any] = {
    "run_profile": "d4f_70d",
    "daily_trading_days": 70,
    "market_history_days": 120,
    "market_history_fallback_days": 180,
    "technical_trading_days": 251,
    "technical_history_days": 550,
    "intraday_interval": "60m",
    "intraday_target_bars_per_day": 15,
    "intraday_recent_full_days": 20,
    "news_limit": 36,
    "llm_scope": "all_nodes",
    "llm_projection": "node_relevant",
    "llm_prompt_token_limit": 128_000,
    "llm_projection_target": 115_000,
    "llm_max_concurrency": 3,
}


def apply_run_profile(state: Mapping[str, Any]) -> dict[str, Any]:
    """Apply named profile defaults without overwriting caller choices."""

    prepared = dict(state)
    if prepared.get("run_profile") == "d4f_70d":
        for key, value in D4F_70D_PROFILE.items():
            prepared.setdefault(key, value)
    return prepared
