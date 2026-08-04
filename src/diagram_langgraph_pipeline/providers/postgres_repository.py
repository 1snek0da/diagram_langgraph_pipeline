"""PostgreSQL persistence for traceable research runs."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Any


class PostgresAnalysisRepository:
    """Persist graph inputs, executions, evidence, decisions, and reports."""

    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("PostgreSQL DSN is required")
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - installation dependent
            raise RuntimeError(
                'Install PostgreSQL support with: pip install -e ".[postgres]"'
            ) from exc
        self._psycopg = psycopg
        self._dsn = dsn

    def _connect(self):
        return self._psycopg.connect(self._dsn)

    def check_health(self) -> dict[str, Any]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT current_database(), inet_server_addr()::text,
                       inet_server_port(), current_setting('server_version'),
                       to_regclass('public.market_bars') IS NOT NULL,
                       to_regclass('public.provider_response_cache') IS NOT NULL
                """
            )
            database, host, port, version, market_ready, cache_ready = cursor.fetchone()
        return {
            "ok": True,
            "database": database,
            "host": host,
            "port": port,
            "version": version,
            "market_schema_ready": market_ready,
            "cache_schema_ready": cache_ready,
        }

    def load_security(self, ticker: str) -> dict[str, Any] | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.ticker, s.company_name, s.market, s.exchange,
                       i.industry_name, s.external_ids_json
                FROM securities s
                LEFT JOIN industries i ON i.id=s.industry_id
                WHERE s.ticker=%s
                """,
                (ticker.upper(),),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "ticker": row[0],
            "company_name": row[1],
            "market": row[2],
            "exchange": row[3],
            "industry_name": row[4],
            "external_ids": row[5] or {},
        }

    def upsert_security_metadata(self, payload: dict[str, Any]) -> None:
        ticker = str(payload["ticker"]).upper()
        industry_name = str(payload.get("industry_name") or "Unknown")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM industries WHERE industry_name=%s AND parent_industry_id IS NULL",
                (industry_name,),
            )
            row = cursor.fetchone()
            if row:
                industry_id = row[0]
            else:
                cursor.execute(
                    "INSERT INTO industries (industry_name) VALUES (%s) RETURNING id",
                    (industry_name,),
                )
                industry_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO securities
                    (ticker, company_name, market, exchange, industry_id, external_ids_json)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (ticker) DO UPDATE SET
                    company_name=EXCLUDED.company_name,
                    market=EXCLUDED.market,
                    exchange=EXCLUDED.exchange,
                    industry_id=EXCLUDED.industry_id,
                    external_ids_json=securities.external_ids_json || EXCLUDED.external_ids_json,
                    updated_at=now()
                """,
                (
                    ticker,
                    payload.get("company_name") or ticker,
                    payload.get("market") or "UNKNOWN",
                    payload.get("exchange") or "UNKNOWN",
                    industry_id,
                    _json_text(payload.get("external_ids", {})),
                ),
            )

    def load_market_data(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        *,
        intraday_interval: str,
    ) -> dict[str, Any]:
        ticker = ticker.upper()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT ON (trade_date)
                    trade_date, open_price, high_price, low_price, close_price,
                    adj_close_price, volume, turnover_amount, turnover_rate, source
                FROM market_bars
                WHERE ticker=%s AND frequency='daily'
                  AND trade_date BETWEEN %s AND %s
                ORDER BY trade_date,
                    CASE WHEN source='yfinance' THEN 0 ELSE 1 END,
                    created_at DESC
                """,
                (ticker, start_date, end_date),
            )
            bars = [
                {
                    "trade_date": row[0].isoformat(),
                    "open": row[1], "high": row[2], "low": row[3],
                    "close": row[4], "adj_close": row[5], "volume": row[6],
                    "turnover_amount": row[7], "turnover_rate": row[8],
                    "source": row[9],
                }
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT DISTINCT ON (bar_time)
                    bar_time, open_price, high_price, low_price, close_price,
                    adj_close_price, volume, source
                FROM intraday_market_bars
                WHERE ticker=%s AND interval=%s
                  AND bar_time >= %s AND bar_time < %s
                ORDER BY bar_time,
                    CASE WHEN source='yfinance' THEN 0 ELSE 1 END,
                    created_at DESC
                """,
                (
                    ticker,
                    intraday_interval,
                    datetime.combine(start_date, datetime.min.time()),
                    datetime.combine(end_date + timedelta(days=1), datetime.min.time()),
                ),
            )
            intraday = [
                {
                    "trade_date": row[0].isoformat(),
                    "open": row[1], "high": row[2], "low": row[3],
                    "close": row[4], "adj_close": row[5], "volume": row[6],
                    "source": row[7],
                }
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """
                SELECT DISTINCT ON (trade_date)
                    trade_date, pe_ttm, pb, ps_ttm, dividend_yield, market_cap, source
                FROM market_valuation_metrics
                WHERE ticker=%s AND trade_date BETWEEN %s AND %s
                ORDER BY trade_date,
                    CASE WHEN source='yfinance' THEN 0 ELSE 1 END,
                    created_at DESC
                """,
                (ticker, start_date, end_date),
            )
            valuations = [
                {
                    "trade_date": row[0].isoformat(), "pe_ttm": row[1],
                    "pb": row[2], "ps_ttm": row[3], "dividend_yield": row[4],
                    "market_cap": row[5], "source": row[6],
                }
                for row in cursor.fetchall()
            ]
        return {
            "bars": bars,
            "minute_bars": intraday,
            "valuations": valuations,
            "source": "postgres_cache",
            "metadata": {
                "intraday_interval": intraday_interval,
                "cache_bar_count": len(bars),
                "cache_intraday_count": len(intraday),
                "cache_valuation_count": len(valuations),
            },
        }

    def save_market_cache(self, ticker: str, payload: dict[str, Any]) -> None:
        self.save_market_data(None, ticker, payload)

    def load_research_cache(
        self,
        provider: str,
        dataset_kind: str,
        scope_hash: str,
        as_of_date: date,
        start_date: date | None,
        end_date: date | None,
        *,
        allow_expired: bool = False,
    ) -> dict[str, Any] | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT response_json, status, coverage_ratio, expires_at,
                       cache_as_of_date, coverage_start, coverage_end, request_json
                FROM provider_response_cache
                WHERE provider=%s AND dataset_kind=%s AND scope_hash=%s
                  AND cache_as_of_date <= %s
                  AND (%s OR expires_at > now())
                  AND (%s::date IS NULL OR coverage_end IS NULL OR coverage_end >= %s)
                  AND (%s::date IS NULL OR coverage_start IS NULL OR coverage_start <= %s)
                ORDER BY cache_as_of_date DESC, updated_at DESC
                LIMIT 1
                """,
                (
                    provider, dataset_kind, scope_hash, as_of_date,
                    allow_expired,
                    start_date, start_date,
                    end_date, end_date,
                ),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "response": row[0], "status": row[1], "coverage_ratio": row[2],
            "expires_at": row[3], "cache_as_of_date": row[4],
            "coverage_start": row[5], "coverage_end": row[6],
            "request": row[7],
        }

    def save_research_cache(self, payload: dict[str, Any]) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO provider_response_cache
                    (provider, dataset_kind, scope_hash, request_json, response_json,
                     cache_as_of_date, coverage_start, coverage_end, status,
                     coverage_ratio, schema_version, expires_at)
                VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (provider, dataset_kind, scope_hash, cache_as_of_date)
                DO UPDATE SET request_json=EXCLUDED.request_json,
                    response_json=EXCLUDED.response_json,
                    coverage_start=EXCLUDED.coverage_start,
                    coverage_end=EXCLUDED.coverage_end,
                    status=EXCLUDED.status,
                    coverage_ratio=EXCLUDED.coverage_ratio,
                    schema_version=EXCLUDED.schema_version,
                    expires_at=EXCLUDED.expires_at,
                    updated_at=now()
                """,
                (
                    payload["provider"], payload["dataset_kind"], payload["scope_hash"],
                    _json_text(payload.get("request", {})),
                    _json_text(payload.get("response", {})),
                    payload["cache_as_of_date"], payload.get("coverage_start"),
                    payload.get("coverage_end"), payload["status"],
                    payload.get("coverage_ratio"), payload.get("schema_version", 1),
                    payload["expires_at"],
                ),
            )

    def load_research_cache_inventory(
        self, ticker: str, as_of_date: date
    ) -> list[dict[str, Any]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT provider, dataset_kind, status, count(*),
                       max(cache_as_of_date), max(coverage_start), max(coverage_end),
                       bool_or(expires_at > now())
                FROM provider_response_cache cache
                WHERE cache_as_of_date <= %s
                  AND EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements(
                          COALESCE(cache.request_json->'entities', '[]'::jsonb)
                      ) entity
                      WHERE upper(entity->>'ticker') = %s
                  )
                GROUP BY provider, dataset_kind, status
                ORDER BY dataset_kind, provider
                """,
                (as_of_date, ticker.upper()),
            )
            rows = cursor.fetchall()
        return [
            {
                "provider": row[0], "dataset_kind": row[1], "status": row[2],
                "entries": row[3], "cache_as_of_date": row[4].isoformat(),
                "coverage_start": row[5].isoformat() if row[5] else None,
                "coverage_end": row[6].isoformat() if row[6] else None,
                "fresh": row[7],
            }
            for row in rows
        ]

    def update_report_path(self, run_id: str, report_path: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE final_reports SET report_path=%s WHERE run_id=%s",
                (report_path, run_id),
            )

    def bootstrap_run(self, state: dict[str, Any]) -> None:
        ticker = str(state["ticker"]).upper()
        industry_name = str(state["industry_name"])
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM industries WHERE industry_name=%s AND parent_industry_id IS NULL LIMIT 1",
                (industry_name,),
            )
            row = cursor.fetchone()
            if row:
                industry_id = row[0]
            else:
                cursor.execute(
                    "INSERT INTO industries (industry_name) VALUES (%s) RETURNING id",
                    (industry_name,),
                )
                industry_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO securities (ticker, company_name, market, exchange, industry_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE SET
                    company_name=EXCLUDED.company_name,
                    industry_id=EXCLUDED.industry_id,
                    updated_at=now()
                """,
                (
                    ticker,
                    state.get("company_name") or ticker,
                    state.get("market", "US"),
                    state.get("exchange", "NASDAQ"),
                    industry_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO analysis_runs
                    (id, ticker, industry_id, as_of_date, investment_horizon,
                     user_request, status, retry_count, max_retries)
                VALUES (%s, %s, %s, %s, %s, %s, 'running', %s, %s)
                ON CONFLICT (id) DO UPDATE SET status='running', updated_at=now()
                """,
                (
                    state["run_id"],
                    ticker,
                    industry_id,
                    state.get("as_of_date") or date.today(),
                    state.get("investment_horizon", "medium"),
                    state.get("user_request"),
                    int(state.get("retry_count", 0)),
                    int(state.get("max_retries", 2)),
                ),
            )

    def record_provider_fetch(
        self,
        run_id: str,
        provider: str,
        dataset_kind: str,
        request_payload: dict[str, Any],
        response_summary: dict[str, Any],
    ) -> None:
        errors = response_summary.get("errors", [])
        warnings = response_summary.get("warnings", [])
        status = "partial" if errors or warnings else "completed"
        coverage = response_summary.get("coverage_ratio")
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO provider_fetch_runs
                    (run_id, provider, dataset_kind, request_json, status,
                     coverage_ratio, warning_json, error_json, ended_at)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s::jsonb, now())
                """,
                (
                    run_id,
                    provider,
                    dataset_kind,
                    _json_text(request_payload),
                    status,
                    coverage,
                    _json_text(warnings),
                    _json_text(errors),
                ),
            )

    def record_node_run(
        self,
        run_id: str,
        node_name: str,
        status: str,
        input_payload: dict[str, Any],
        output_payload: dict[str, Any] | None,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM node_runs WHERE run_id=%s AND node_name=%s",
                (run_id, node_name),
            )
            attempt_no = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO node_runs
                    (run_id, node_name, attempt_no, status, ended_at, error_message,
                     input_json, output_json)
                VALUES (%s, %s, %s, %s, now(), %s, %s::jsonb, %s::jsonb)
                """,
                (
                    run_id,
                    node_name,
                    attempt_no,
                    status,
                    error_message,
                    _json_text(input_payload),
                    _json_text(output_payload or {}),
                ),
            )

    def save_market_data(
        self, run_id: str | None, ticker: str, payload: dict[str, Any]
    ) -> None:
        source = str(payload.get("source", "unknown"))
        bars = payload.get("technical_bars") or payload.get("bars", [])
        intraday_bars = payload.get("minute_bars", [])
        valuations = payload.get("valuations", [])
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO securities (ticker, company_name, market, exchange)
                VALUES (%s,%s,'US','UNKNOWN') ON CONFLICT (ticker) DO NOTHING
                """,
                (ticker, ticker),
            )
            for bar in bars:
                cursor.execute(
                    """
                    INSERT INTO market_bars
                        (ticker, trade_date, frequency, open_price, high_price, low_price,
                         close_price, adj_close_price, volume, turnover_amount, turnover_rate, source)
                    VALUES (%s, %s, 'daily', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, trade_date, frequency, source) DO UPDATE SET
                        open_price=EXCLUDED.open_price, high_price=EXCLUDED.high_price,
                        low_price=EXCLUDED.low_price, close_price=EXCLUDED.close_price,
                        adj_close_price=EXCLUDED.adj_close_price, volume=EXCLUDED.volume
                    """,
                    (
                        ticker,
                        str(bar.get("trade_date", ""))[:10],
                        bar.get("open"),
                        bar.get("high"),
                        bar.get("low"),
                        bar.get("close"),
                        bar.get("adj_close"),
                        bar.get("volume"),
                        bar.get("turnover_amount"),
                        bar.get("turnover_rate"),
                        source,
                    ),
                )
            interval = str(payload.get("metadata", {}).get("intraday_interval") or "1m")
            for bar in intraday_bars:
                cursor.execute(
                    """
                    INSERT INTO intraday_market_bars
                        (run_id, ticker, bar_time, interval, open_price, high_price,
                         low_price, close_price, adj_close_price, volume, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (ticker, bar_time, interval, source) DO UPDATE SET
                        run_id=EXCLUDED.run_id, open_price=EXCLUDED.open_price,
                        high_price=EXCLUDED.high_price, low_price=EXCLUDED.low_price,
                        close_price=EXCLUDED.close_price,
                        adj_close_price=EXCLUDED.adj_close_price, volume=EXCLUDED.volume
                    """,
                    (
                        run_id,
                        ticker,
                        bar.get("trade_date"),
                        interval,
                        bar.get("open"),
                        bar.get("high"),
                        bar.get("low"),
                        bar.get("close"),
                        bar.get("adj_close"),
                        bar.get("volume"),
                        source,
                    ),
                )
            for item in valuations:
                cursor.execute(
                    """
                    INSERT INTO market_valuation_metrics
                        (ticker, trade_date, pe_ttm, pb, ps_ttm, dividend_yield, market_cap, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, trade_date, source) DO UPDATE SET
                        pe_ttm=EXCLUDED.pe_ttm, pb=EXCLUDED.pb, ps_ttm=EXCLUDED.ps_ttm,
                        dividend_yield=EXCLUDED.dividend_yield, market_cap=EXCLUDED.market_cap
                    """,
                    (
                        ticker,
                        item.get("trade_date"),
                        item.get("pe_ttm"),
                        item.get("pb"),
                        item.get("ps_ttm"),
                        item.get("dividend_yield"),
                        item.get("market_cap"),
                        source,
                    ),
                )

    def save_final_report(self, run_id: str, report_markdown: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO final_reports (run_id, report_markdown)
                VALUES (%s, %s)
                ON CONFLICT (run_id) DO UPDATE SET report_markdown=EXCLUDED.report_markdown
                """,
                (run_id, report_markdown),
            )

    def record_llm_invocation(
        self, run_id: str, node_name: str, payload: dict[str, Any]
    ) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM llm_invocations WHERE run_id=%s AND node_name=%s",
                (run_id, node_name),
            )
            attempt_no = cursor.fetchone()[0]
            usage = payload.get("usage", {})
            cursor.execute(
                """
                INSERT INTO llm_invocations
                    (run_id, node_name, attempt_no, status, provider, model, request_id,
                     input_hash, candidate_char_count, projected_char_count,
                     estimated_prompt_tokens, prompt_tokens, completion_tokens,
                     cached_tokens, usage_json, projection_manifest_json,
                     error_type, error_message, cache_hit, ended_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s::jsonb,%s::jsonb,%s,%s,%s,now())
                """,
                (
                    run_id,
                    node_name,
                    attempt_no,
                    payload.get("status", "failed"),
                    payload.get("provider"),
                    payload.get("model"),
                    payload.get("request_id"),
                    payload.get("input_hash"),
                    payload.get("candidate_char_count"),
                    payload.get("projected_char_count"),
                    payload.get("estimated_prompt_tokens"),
                    usage.get("prompt_tokens"),
                    usage.get("completion_tokens"),
                    usage.get("cached_tokens")
                    or usage.get("prompt_cache_hit_tokens"),
                    _json_text(usage),
                    _json_text(payload.get("projection_manifest", {})),
                    payload.get("error_type"),
                    payload.get("error_message"),
                    bool(payload.get("cache_hit")),
                ),
            )

    def save_analysis_result(self, state: dict[str, Any]) -> None:
        run_id = str(state["run_id"])
        ticker = str(state["ticker"])
        market = state.get("stock_market_data_analysis", {})
        technical = state.get("stock_technical_result", {})
        sentiment = state.get("sentiment_result", {})
        decision = state.get("decision_result", {})
        review = state.get("review_result", {})
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO stock_market_analysis
                    (run_id, ticker, analysis_window, return_5d, return_20d, return_60d,
                     return_120d, return_250d, volatility_20d, max_drawdown, atr_json,
                     ma_status_json, volume_price_signal, valuation_percentile_json,
                     relative_strength_json, abnormal_events_json, data_coverage_json, raw_payload_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,
                        %s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb)
                ON CONFLICT (run_id) DO UPDATE SET raw_payload_json=EXCLUDED.raw_payload_json
                RETURNING id
                """,
                (
                    run_id,
                    ticker,
                    market.get("analysis_window", "custom"),
                    market.get("return_5d"),
                    market.get("return_20d"),
                    market.get("return_60d"),
                    market.get("return_120d"),
                    market.get("return_250d"),
                    market.get("volatility_20d"),
                    market.get("max_drawdown"),
                    _json_text(market.get("atr14", {})),
                    _json_text(market.get("ma_status", {})),
                    _json_text(market.get("volume_price_signal", {})),
                    _json_text(market.get("valuation_percentile", {})),
                    _json_text(market.get("relative_strength", {})),
                    _json_text(market.get("abnormal_events", [])),
                    _json_text(market.get("data_coverage", {})),
                    _json_text(market),
                ),
            )
            market_analysis_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO technical_analysis
                    (run_id, target_type, target_code, trend, support_price, resistance_price,
                     volume_signal, pattern_name, cycle_position, raw_payload_json)
                VALUES (%s,'stock',%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (run_id, target_type, target_code) DO UPDATE SET raw_payload_json=EXCLUDED.raw_payload_json
                """,
                (
                    run_id,
                    ticker,
                    technical.get("trend"),
                    technical.get("support_price"),
                    technical.get("resistance_price"),
                    technical.get("volume_signal"),
                    technical.get("pattern_name"),
                    technical.get("cycle_position"),
                    _json_text(technical),
                ),
            )
            cursor.execute(
                "SELECT industry_id FROM analysis_runs WHERE id=%s", (run_id,)
            )
            industry_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO sentiment_analysis
                    (run_id, ticker, industry_id, sentiment_score, heat_score, crowding_risk,
                     positive_items_json, negative_items_json, raw_payload_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
                ON CONFLICT (run_id) DO UPDATE SET raw_payload_json=EXCLUDED.raw_payload_json
                """,
                (
                    run_id,
                    ticker,
                    industry_id,
                    sentiment.get("sentiment_score"),
                    sentiment.get("heat_score"),
                    sentiment.get("crowding_risk"),
                    _json_text(sentiment.get("positive_items", [])),
                    _json_text(sentiment.get("negative_items", [])),
                    _json_text(sentiment),
                ),
            )
            cursor.execute(
                """
                INSERT INTO decision_records
                    (run_id, ticker, stock_market_analysis_id, action_bias, conviction, buy_zone,
                     sell_zone, invalid_condition, supporting_points_json, risk_points_json,
                     confidence_score, raw_payload_json)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb)
                ON CONFLICT (run_id) DO UPDATE SET raw_payload_json=EXCLUDED.raw_payload_json
                RETURNING id
                """,
                (
                    run_id,
                    ticker,
                    market_analysis_id,
                    decision.get("action_bias", "watch"),
                    decision.get("conviction", "low"),
                    _json_text(decision.get("buy_zone", {})),
                    _json_text(decision.get("sell_zone", {})),
                    decision.get("invalid_condition"),
                    _json_text(decision.get("supporting_points", [])),
                    _json_text(decision.get("risk_points", [])),
                    decision.get("confidence_score"),
                    _json_text(decision),
                ),
            )
            decision_id = cursor.fetchone()[0]
            self._save_evidence(cursor, state, decision_id)
            attempt_no = int(state.get("retry_count", 0)) + 1
            cursor.execute(
                """
                INSERT INTO review_records
                    (run_id, attempt_no, passed, completeness_score, evidence_score, logic_score,
                     missing_items_json, retry_tasks_json, review_comment)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                ON CONFLICT (run_id, attempt_no) DO UPDATE SET review_comment=EXCLUDED.review_comment
                """,
                (
                    run_id,
                    attempt_no,
                    bool(review.get("passed")),
                    review.get("completeness_score"),
                    review.get("evidence_score"),
                    review.get("logic_score"),
                    _json_text(review.get("missing_items", [])),
                    _json_text(review.get("retry_tasks", [])),
                    review.get("review_comment"),
                ),
            )
            cursor.execute(
                "UPDATE analysis_runs SET status='completed', retry_count=%s, updated_at=now() WHERE id=%s",
                (int(state.get("retry_count", 0)), run_id),
            )

    def _save_evidence(self, cursor, state: dict[str, Any], decision_id: Any) -> None:
        for item in state.get("evidence_refs", []):
            source_id = str(item.get("source_id", "input"))
            metadata = item.get("metadata", {})
            provider = str(metadata.get("provider", source_id.split(":", 1)[0]))
            content_hash = sha256(source_id.encode("utf-8")).hexdigest()
            cursor.execute(
                """
                INSERT INTO source_documents
                    (provider, source_tier, source_type, external_id, title, url,
                     content_hash, language, license_scope, metadata_json)
                VALUES (%s,'secondary',%s,%s,%s,%s,%s,'en-US','public',%s::jsonb)
                ON CONFLICT (content_hash) DO UPDATE SET retrieved_at=now()
                RETURNING id
                """,
                (
                    provider,
                    item.get("evidence_type", "research"),
                    source_id,
                    f"{provider} source for {state['ticker']}",
                    metadata.get("url"),
                    content_hash,
                    _json_text(metadata),
                ),
            )
            document_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO evidence_items
                    (id, document_id, run_id, ticker, evidence_type, claim_text,
                     confidence_score, page_no, paragraph_ref, metric_key,
                     extraction_method, quote_text)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET claim_text=EXCLUDED.claim_text
                """,
                (
                    item.get("evidence_id"),
                    document_id,
                    state["run_id"],
                    state["ticker"],
                    item.get("evidence_type", "research"),
                    item.get("claim_text", ""),
                    item.get("confidence_score"),
                    item.get("page_no"),
                    item.get("paragraph_ref"),
                    item.get("metric_key"),
                    item.get("extraction_method", "provided"),
                    item.get("quote_text"),
                ),
            )
            cursor.execute(
                """
                INSERT INTO decision_evidence_links (decision_id, evidence_id, relationship)
                VALUES (%s,%s,'support') ON CONFLICT DO NOTHING
                """,
                (decision_id, item.get("evidence_id")),
            )

    def mark_run_failed(self, run_id: str, error_message: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE analysis_runs SET status='failed', updated_at=now(), user_request=COALESCE(user_request,'') || %s WHERE id=%s",
                (f"\nFailure: {error_message[:500]}", run_id),
            )


def _json_text(value: Any) -> str:
    import json

    return json.dumps(_jsonable(value), ensure_ascii=False, separators=(",", ":"))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
