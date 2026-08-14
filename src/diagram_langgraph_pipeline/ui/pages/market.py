"""Market chart view backed by the API market-bars endpoint."""

from __future__ import annotations

from datetime import date

import plotly.graph_objects as go

from ..components import page_heading


def render(st, gateway, state) -> None:
    page_heading(st, "行情视图", "查看 API 返回的日线行情，不虚构价格或指标。")
    ticker = st.text_input("证券代码", value="").strip().upper()
    start_date = st.date_input("开始日期", value=date.today())
    end_date = st.date_input("结束日期", value=date.today())
    if not ticker:
        st.info("输入证券代码后加载行情。")
        return
    chart = gateway.get_market_chart(ticker, start_date, end_date)
    if not chart.bars:
        st.info("没有可显示的行情数据。")
        return
    dates = [bar.trade_date for bar in chart.bars]
    figure = go.Figure()
    figure.add_trace(
        go.Candlestick(
            x=dates,
            open=[bar.open for bar in chart.bars],
            high=[bar.high for bar in chart.bars],
            low=[bar.low for bar in chart.bars],
            close=[bar.close for bar in chart.bars],
            name="价格",
        )
    )
    figure.add_trace(
        go.Bar(
            x=dates,
            y=[bar.volume or 0 for bar in chart.bars],
            name="成交量",
            yaxis="y2",
        )
    )
    figure.update_layout(
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        yaxis2={"overlaying": "y", "side": "right", "showgrid": False},
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
    )
    if chart.source:
        st.caption(f"数据源：{chart.source}")
    st.plotly_chart(figure, use_container_width=True)

