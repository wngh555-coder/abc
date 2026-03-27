"""
HR 적임자 선발 대시보드 — Plotly 비교·요약 차트.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from hr_data import radar_metrics


def fig_radar_compare(df: pd.DataFrame, id_col: str = "employee_ref") -> go.Figure:
    if df.empty:
        return go.Figure().update_layout(title="비교할 후보를 선택하세요.", height=420)
    fig = go.Figure()
    colors = ["#22c55e", "#3b82f6", "#eab308", "#a855f7", "#ef4444"]
    keys_order = ["영어(정규화)", "근속(정규화)", "해외경험(정규화)", "출장적합(자가)"]
    for i, (_, row) in enumerate(df.iterrows()):
        m = radar_metrics(row)
        vals = [m[k] for k in keys_order] + [m[keys_order[0]]]
        theta = keys_order + [keys_order[0]]
        fig.add_trace(
            go.Scatterpolar(
                r=vals,
                theta=theta,
                fill="toself",
                name=str(row[id_col]),
                line_color=colors[i % len(colors)],
                opacity=0.55,
            )
        )
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        title="선택 후보 비교 (정규화 지표 · 참고용)",
        height=460,
        margin=dict(l=48, r=48, t=56, b=48),
        legend=dict(orientation="h", yanchor="bottom", y=-0.15),
    )
    return fig


def fig_compliance_bars(summary: pd.DataFrame) -> go.Figure:
    if summary.empty:
        return go.Figure().update_layout(title="요건 충족 요약", height=360)
    fig = go.Figure(
        go.Bar(
            x=summary["요건"],
            y=summary["충족률_%"],
            marker_color="#3b82f6",
            text=summary["충족률_%"].astype(str) + "%",
            textposition="outside",
        )
    )
    fig.update_layout(
        title="필수 요건 충족률 (현재 필터 집단)",
        yaxis=dict(title="충족률 (%)", range=[0, 105]),
        height=400,
        margin=dict(l=48, r=24, t=48, b=120),
        xaxis=dict(tickangle=-25),
    )
    return fig


def fig_fit_score_bars(df: pd.DataFrame, id_col: str = "employee_ref") -> go.Figure:
    if df.empty:
        return go.Figure().update_layout(title="우대 반영 점수", height=360)
    d = df.sort_values("fit_score_0_100", ascending=True)
    colors = ["#22c55e" if m else "#fca5a5" for m in d["meets_required"]]
    fig = go.Figure(
        go.Bar(
            y=d[id_col].astype(str),
            x=d["fit_score_0_100"],
            orientation="h",
            marker_color=colors,
            text=d["fit_score_0_100"].astype(str),
            textposition="outside",
        )
    )
    fig.update_layout(
        title="우대 규칙 반영 점수 (필수 미충족 시 0)",
        xaxis=dict(title="점수 (0–100)", range=[0, 105]),
        height=min(420, 80 + 28 * len(d)),
        margin=dict(l=120, r=48, t=48, b=48),
    )
    return fig
