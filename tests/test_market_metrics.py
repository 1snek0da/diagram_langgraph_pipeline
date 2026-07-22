from diagram_langgraph_pipeline.analysis.market_metrics import analyze_market_payload
from diagram_langgraph_pipeline.demo_data import make_market_payload


def test_market_metrics_cover_all_required_dimensions():
    stock = make_market_payload(20.0, 0.001)
    benchmark = make_market_payload(100.0, 0.0002)
    sector = make_market_payload(50.0, 0.0005)

    result = analyze_market_payload(stock, benchmark, sector)

    for window in (5, 20, 60, 120, 250):
        assert result[f"return_{window}d"] is not None
    for window in (20, 60, 120, 250):
        assert result["ma_status"][f"ma{window}"]["value"] is not None
    assert result["volatility_20d"] is not None
    assert result["max_drawdown"] is not None
    assert result["atr14"]["value"] is not None
    assert result["valuation_percentile"]["pe_ttm"]["sample_size"] == 320
    assert result["relative_strength"]["vs_benchmark"]["excess_return_250d"] is not None
    assert result["data_coverage"]["coverage_ratio"] == 1.0


def test_missing_market_data_is_explicit():
    result = analyze_market_payload({"bars": [], "valuations": [], "source": "empty"})

    assert result["return_20d"] is None
    assert result["data_coverage"]["coverage_ratio"] == 0.0
    assert len(result["data_coverage"]["missing_items"]) >= 4
