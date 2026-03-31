"""
가상 투자 대시보드 Plotly 차트.
기획: docs/virtual-investment-game-dashboard-plan.md — 시세 라인, 자산 곡선, 배분.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def fig_price_line(df: pd.DataFrame, symbol: str) -> go.Figure:
    if df.empty or "Close" not in df.columns:
        fig = go.Figure()
        fig.update_layout(
            title=f"{symbol} 시세 없음",
            height=400,
            margin=dict(l=48, r=24, t=48, b=48),
        )
        return fig
    fig = px.line(
        df,
        x="Date",
        y="Close",
        labels={"Close": "종가 (USD)", "Date": "일자"},
        height=400,
    )
    fig.update_traces(line=dict(width=2))
    fig.update_layout(
        title=f"{symbol} 종가",
        margin=dict(l=48, r=24, t=48, b=48),
        xaxis_title=None,
    )
    return fig


def fig_equity_curve(snapshots: list) -> go.Figure:
    if not snapshots:
        return go.Figure().update_layout(title="자산 곡선", height=360)
    dfp = pd.DataFrame(snapshots)
    if "ts" not in dfp.columns or "equity" not in dfp.columns:
        return go.Figure().update_layout(title="자산 곡선", height=360)
    dfp = dfp.copy()
    dfp["ts"] = pd.to_datetime(dfp["ts"], errors="coerce")
    dfp = dfp.dropna(subset=["ts"])
    fig = px.line(
        dfp,
        x="ts",
        y="equity",
        labels={"equity": "총 자산 (USD)", "ts": "시각"},
        height=360,
    )
    fig.update_traces(line=dict(width=2, color="#22c55e"))
    fig.update_layout(title="자산 곡선 (거래·초기 시점 스냅샷)", margin=dict(l=48, r=24, t=48, b=48))
    return fig


def fig_allocation(cash: float, position_values: dict[str, float]) -> go.Figure:
    names = ["현금"]
    values = [max(0.0, cash)]
    for sym, v in sorted(position_values.items()):
        if v > 0:
            names.append(sym)
            values.append(v)
    if sum(values) <= 0:
        return go.Figure().update_layout(title="자산 배분", height=360)
    fig = go.Figure(
        data=[
            go.Pie(
                labels=names,
                values=values,
                hole=0.35,
                textinfo="label+percent",
            )
        ]
    )
    fig.update_layout(title="자산 배분 (평가 기준)", height=360, margin=dict(l=24, r=24, t=48, b=24))
    return fig
