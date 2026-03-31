"""
직책자 프로파일 — Plotly 차트.
"""

from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import pandas as pd

from leader_profile_io import RATER_LABELS_KR, others_only


def fig_radar_latest(df_emp_360: pd.DataFrame, year: int) -> go.Figure:
    sub = df_emp_360[df_emp_360["cycle_year"] == year]
    if sub.empty:
        fig = go.Figure()
        fig.update_layout(title="데이터 없음", height=420)
        return fig

    piv = sub.pivot_table(index="dimension", columns="rater_type", values="score", aggfunc="mean")
    dims = list(piv.index)
    fig = go.Figure()
    colors = {
        "self": "#636EFA",
        "manager": "#EF553B",
        "peer": "#00CC96",
        "direct": "#AB63FA",
    }
    for col in ["self", "manager", "peer", "direct"]:
        if col not in piv.columns:
            continue
        vals = [float(piv.loc[d, col]) if d in piv.index and pd.notna(piv.loc[d, col]) else None for d in dims]
        if all(v is None for v in vals):
            continue
        label = RATER_LABELS_KR.get(col, col)
        fig.add_trace(
            go.Scatterpolar(
                r=vals + [vals[0]],
                theta=dims + [dims[0]],
                fill="toself",
                name=label,
                line_color=colors.get(col, "#333"),
                opacity=0.55,
            )
        )
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[2.5, 5.0])),
        showlegend=True,
        legend_orientation="h",
        legend_yanchor="bottom",
        legend_y=-0.2,
        title=f"{year}년 다면진단 — 역량별 · 평가자 유형",
        height=480,
        margin=dict(t=60, b=80),
    )
    return fig


def fig_trend_others_by_dimension(df_emp_360: pd.DataFrame) -> go.Figure:
    o = others_only(df_emp_360)
    if o.empty:
        return go.Figure(layout=dict(title="타 평가자 데이터 없음", height=400))
    g = o.groupby(["cycle_year", "dimension"], as_index=False)["score"].mean()
    fig = px.line(
        g,
        x="cycle_year",
        y="score",
        color="dimension",
        markers=True,
        labels={"cycle_year": "연도", "score": "평균 점수", "dimension": "역량"},
    )
    fig.update_layout(
        title="연도별 추이 (타 평가자 평균)",
        yaxis_range=[2.5, 5.0],
        height=440,
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, x=0),
    )
    return fig


def fig_gap_self_vs_others(df_emp_360: pd.DataFrame, year: int) -> go.Figure:
    sub = df_emp_360[df_emp_360["cycle_year"] == year]
    if sub.empty:
        return go.Figure(layout=dict(title="데이터 없음", height=400))
    rows = []
    for dim, g in sub.groupby("dimension"):
        slf = g[g["rater_type"] == "self"]["score"].mean()
        oth = g[g["rater_type"] != "self"]["score"].mean()
        if pd.notna(slf) and pd.notna(oth):
            rows.append({"dimension": dim, "본인": float(slf), "타 평균": float(oth)})
    if not rows:
        return go.Figure(layout=dict(title="집계 불가", height=400))
    t = pd.DataFrame(rows).sort_values("dimension")
    fig = go.Figure()
    fig.add_bar(name="본인", x=t["dimension"], y=t["본인"], marker_color="#636EFA")
    fig.add_bar(name="타 평가자 평균", x=t["dimension"], y=t["타 평균"], marker_color="#B6B6D8")
    fig.update_layout(
        barmode="group",
        title=f"{year}년 본인 vs 타 평가자 평균",
        yaxis_range=[2.5, 5.0],
        height=420,
        xaxis_title="역량",
        yaxis_title="점수",
    )
    return fig


def fig_review_bands(df_emp_rev: pd.DataFrame) -> go.Figure:
    if df_emp_rev.empty:
        return go.Figure(layout=dict(title="인사평가 데이터 없음", height=320))
    t = df_emp_rev.sort_values("year")
    order = ["C", "B", "B+", "A", "S"]
    band_to_y = {b: i for i, b in enumerate(order)}
    ys = [band_to_y.get(str(b), 2) for b in t["rating_band"]]
    fig = go.Figure(
        go.Scatter(
            x=t["year"],
            y=ys,
            mode="lines+markers+text",
            text=t["rating_band"],
            textposition="top center",
            line=dict(width=2, color="#00CC96"),
            marker=dict(size=10),
        )
    )
    fig.update_layout(
        title="인사평가 등급 추이",
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(order))),
            ticktext=order,
            range=[-0.5, len(order) - 0.5],
        ),
        xaxis=dict(dtick=1),
        height=360,
        margin=dict(t=50, b=40),
    )
    return fig


def fig_rater_breakdown_small_multiples(df_emp_360: pd.DataFrame, year: int) -> go.Figure:
    """역량별로 평가자 유형 막대."""
    sub = df_emp_360[df_emp_360["cycle_year"] == year]
    if sub.empty:
        return go.Figure(layout=dict(title="데이터 없음", height=300))

    dims = sorted(sub["dimension"].unique())
    n = len(dims)
    cols = min(3, n)
    rows = (n + cols - 1) // cols
    fig = make_subplots(
        rows=rows,
        cols=cols,
        subplot_titles=dims,
        vertical_spacing=0.12,
        horizontal_spacing=0.08,
    )
    rater_order = ["manager", "peer", "direct", "self"]
    color_map = {"manager": "#EF553B", "peer": "#00CC96", "direct": "#AB63FA", "self": "#636EFA"}
    for i, dim in enumerate(dims):
        r, c = i // cols + 1, i % cols + 1
        g = sub[sub["dimension"] == dim]
        means = g.groupby("rater_type")["score"].mean()
        rt_list = [rt for rt in rater_order if rt in means.index]
        xs = [RATER_LABELS_KR.get(rt, rt) for rt in rt_list]
        ys = [float(means[rt]) for rt in rt_list]
        cols_bar = [color_map.get(rt, "#888") for rt in rt_list]
        fig.add_trace(
            go.Bar(x=xs, y=ys, marker_color=cols_bar, showlegend=False),
            row=r,
            col=c,
        )
        fig.update_yaxes(range=[2.5, 5.0], row=r, col=c)
    fig.update_layout(height=200 * rows + 80, title_text=f"{year}년 역량별 평가자 유형 분해", showlegend=False)
    return fig
