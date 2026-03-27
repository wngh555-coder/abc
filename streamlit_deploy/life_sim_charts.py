"""
인생 시뮬레이터 대시보드 Plotly 차트.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from life_sim_state import STAT_LABELS_KO

_STAT_COLORS = ("#22c55e", "#3b82f6", "#eab308", "#a855f7", "#f43f5e")
_FILL_ALPHAS = (
    "rgba(34,197,94,0.18)",
    "rgba(59,130,246,0.15)",
    "rgba(234,179,8,0.15)",
    "rgba(168,85,247,0.15)",
    "rgba(244,63,94,0.15)",
)
_LAYOUT_BASE = dict(
    template="plotly_white",
    font=dict(family="Arial, 'Malgun Gothic', sans-serif", size=12, color="#1e293b"),
    paper_bgcolor="rgba(248,250,252,0.95)",
    plot_bgcolor="rgba(255,255,255,0.9)",
)


def _stat_keys_labels(scenario: dict[str, Any]) -> tuple[tuple[str, ...], list[str]]:
    keys = tuple(scenario.get("stat_keys") or ())
    labels = [STAT_LABELS_KO.get(k, k) for k in keys]
    return keys, labels


def _timeline_df(state: dict[str, Any], scenario: dict[str, Any]) -> pd.DataFrame:
    keys, _ = _stat_keys_labels(scenario)
    age0 = int(scenario["starting_age"])
    apt = int(scenario["age_per_turn"])
    rows = []
    for e in state.get("timeline") or []:
        t = int(e["turn"])
        sa = e.get("stats_after") or {}
        row = {"turn": t, "나이": age0 + t * apt}
        for k in keys:
            row[STAT_LABELS_KO.get(k, k)] = float(sa.get(k, 0))
        rows.append(row)
    return pd.DataFrame(rows)


def fig_stat_lines(state: dict[str, Any], scenario: dict[str, Any]) -> go.Figure:
    keys, ycols = _stat_keys_labels(scenario)
    if not keys:
        return go.Figure().update_layout(title="점수가 어떻게 변했는지", height=400, **_LAYOUT_BASE)
    df = _timeline_df(state, scenario)
    if df.empty:
        return go.Figure().update_layout(title="점수가 어떻게 변했는지", height=400, **_LAYOUT_BASE)
    fig = go.Figure()
    for i, col in enumerate(ycols):
        if col not in df.columns:
            continue
        c = _STAT_COLORS[i % len(_STAT_COLORS)]
        extra = {}
        if i == 0:
            extra = dict(fill="tozeroy", fillcolor=_FILL_ALPHAS[0])
        fig.add_trace(
            go.Scatter(
                x=df["나이"],
                y=df[col],
                name=col,
                mode="lines+markers",
                line=dict(width=2.5, color=c, shape="spline", smoothing=0.35),
                marker=dict(size=7, line=dict(width=1, color="white")),
                **extra,
            )
        )
    fig.update_layout(
        title=dict(text="나이에 따른 점수 변화", font=dict(size=16)),
        height=400,
        margin=dict(l=52, r=28, t=56, b=48),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
        xaxis_title="나이",
        yaxis_title="점수 (0~100)",
        yaxis=dict(range=[0, 100], gridcolor="rgba(148,163,184,0.35)"),
        xaxis=dict(gridcolor="rgba(148,163,184,0.2)"),
        **_LAYOUT_BASE,
    )
    return fig


def fig_radar(stats: dict[str, float], scenario: dict[str, Any]) -> go.Figure:
    keys, labels = _stat_keys_labels(scenario)
    values = [float(stats.get(k, 0)) for k in keys]
    if not keys:
        return go.Figure().update_layout(title="지금 점수", height=400, **_LAYOUT_BASE)
    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=[50] * len(labels) + [50],
            theta=labels + [labels[0]],
            name="기준(50)",
            line=dict(color="rgba(148,163,184,0.85)", width=1.5, dash="dash"),
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=values + [values[0]],
            theta=labels + [labels[0]],
            name="지금",
            line=dict(color="#0d9488", width=2.5),
            fillcolor="rgba(13, 148, 136, 0.35)",
            fill="toself",
        )
    )
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100], gridcolor="rgba(100,116,139,0.25)")),
        title=dict(text="지금 점수 (레이더, 가운데 50은 기준)", font=dict(size=16)),
        height=420,
        margin=dict(l=48, r=48, t=56, b=48),
        showlegend=True,
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
        **_LAYOUT_BASE,
    )
    return fig


def fig_current_bars(stats: dict[str, float], scenario: dict[str, Any]) -> go.Figure:
    keys, labels = _stat_keys_labels(scenario)
    if not keys:
        return go.Figure().update_layout(title="지금 점수", height=320, **_LAYOUT_BASE)
    vals = [float(stats.get(k, 0)) for k in keys]
    colors = [_STAT_COLORS[i % len(_STAT_COLORS)] for i in range(len(keys))]
    fig = go.Figure(
        go.Bar(
            x=vals,
            y=labels,
            orientation="h",
            marker=dict(color=colors, line=dict(color="white", width=1)),
            text=[f"{v:.0f}" for v in vals],
            textposition="auto",
        )
    )
    fig.update_layout(
        title=dict(text="지금 점수 막대", font=dict(size=16)),
        xaxis=dict(range=[0, 100], title="점수", gridcolor="rgba(148,163,184,0.35)"),
        yaxis=dict(title=""),
        height=max(280, 56 + len(keys) * 44),
        margin=dict(l=120, r=40, t=52, b=48),
        **_LAYOUT_BASE,
    )
    return fig


def fig_timeline_heatmap(state: dict[str, Any], scenario: dict[str, Any]) -> go.Figure:
    keys, labels = _stat_keys_labels(scenario)
    if not keys:
        return go.Figure().update_layout(title="색으로 보는 표", height=360, **_LAYOUT_BASE)
    df = _timeline_df(state, scenario)
    if df.empty:
        return go.Figure().update_layout(title="색으로 보는 표", height=360, **_LAYOUT_BASE)
    z = []
    for col in labels:
        z.append(df[col].tolist() if col in df.columns else [0.0] * len(df))
    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=[f"{a}세" for a in df["나이"].tolist()],
            y=labels,
            colorscale="Tealgrn",
            zmin=0,
            zmax=100,
            colorbar=dict(title="점수"),
        )
    )
    fig.update_layout(
        title=dict(text="나이마다 점수 (색이 진할수록 높음)", font=dict(size=16)),
        xaxis=dict(title="나이", side="bottom"),
        yaxis=dict(title=""),
        height=max(320, 120 + len(keys) * 36),
        margin=dict(l=100, r=60, t=52, b=80),
        **_LAYOUT_BASE,
    )
    return fig


def fig_turn_deltas(state: dict[str, Any], scenario: dict[str, Any]) -> go.Figure:
    """각 턴에서 직전 대비 스탯 변화량(막대 누적)."""
    keys, labels = _stat_keys_labels(scenario)
    timeline = state.get("timeline") or []
    if len(keys) < 1 or len(timeline) < 2:
        return go.Figure().update_layout(title="한 번 고를 때마다 바뀐 점수", height=360, **_LAYOUT_BASE)

    x_labels: list[str] = []
    series: dict[str, list[float]] = {lb: [] for lb in labels}
    for i in range(1, len(timeline)):
        prev = timeline[i - 1].get("stats_after") or {}
        cur = timeline[i].get("stats_after") or {}
        turn = int(timeline[i].get("turn", i))
        lbl = timeline[i].get("choice_label") or f"턴{turn}"
        if len(lbl) > 14:
            lbl = lbl[:12] + "…"
        x_labels.append(f"T{turn}\n{lbl}")
        for ki, k in enumerate(keys):
            d = float(cur.get(k, 0)) - float(prev.get(k, 0))
            series[labels[ki]].append(d)

    fig = go.Figure()
    for i, lb in enumerate(labels):
        fig.add_trace(
            go.Bar(
                name=lb,
                x=x_labels,
                y=series[lb],
                marker_color=_STAT_COLORS[i % len(_STAT_COLORS)],
            )
        )
    fig.update_layout(
        barmode="relative",
        title=dict(text="한 번 고를 때마다 (직전보다 얼마나)", font=dict(size=16)),
        xaxis=dict(title="", tickangle=-35),
        yaxis=dict(title="얼마나 바뀌었나", zeroline=True, zerolinewidth=2, zerolinecolor="#64748b"),
        height=420,
        margin=dict(l=52, r=28, t=56, b=120),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=1, xanchor="right"),
        **_LAYOUT_BASE,
    )
    return fig


def fig_sparkline_grid(state: dict[str, Any], scenario: dict[str, Any]) -> go.Figure:
    """스탯별 세로 스택 미니 추이."""
    keys, labels = _stat_keys_labels(scenario)
    df = _timeline_df(state, scenario)
    if df.empty or not keys:
        return go.Figure().update_layout(title="항목별로 보기", height=240, **_LAYOUT_BASE)

    n = len(keys)
    fig = make_subplots(
        rows=n,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=labels,
    )
    for i, k in enumerate(keys):
        col = STAT_LABELS_KO.get(k, k)
        if col not in df.columns:
            continue
        c = _STAT_COLORS[i % len(_STAT_COLORS)]
        fig.add_trace(
            go.Scatter(
                x=df["나이"],
                y=df[col],
                mode="lines+markers",
                line=dict(width=2, color=c),
                marker=dict(size=5),
                showlegend=False,
            ),
            row=i + 1,
            col=1,
        )
    fig.update_yaxes(range=[0, 100], gridcolor="rgba(148,163,184,0.25)")
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.15)")
    fig.update_layout(
        title=dict(text="항목별 줄그래프 (가로축은 나이)", font=dict(size=16)),
        height=min(520, 72 * n + 100),
        margin=dict(l=44, r=24, t=80, b=40),
        **_LAYOUT_BASE,
    )
    return fig
