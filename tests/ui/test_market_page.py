from diagram_langgraph_pipeline.ui.pages.market import render

from .fakes import FakeGateway, FakeStreamlit, sample_market_chart


def test_market_page_renders_candles_and_volume():
    gateway = FakeGateway(market_chart=sample_market_chart())
    st = FakeStreamlit(values={"证券代码": "AAPL"})

    render(st, gateway, {})

    figure = st.plotly_figures[0]
    assert {trace.type for trace in figure.data} == {"candlestick", "bar"}

