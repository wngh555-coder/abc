"""
사내 인사 통계 대시보드: Plotly 차트 빌더
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from hr_employee_io import COL_LABELS


def fig_headcount_by_dept(filtered: pd.DataFrame) -> go.Figure:
    g = filtered.groupby("dept", as_index=False).size().rename(columns={"size": "인원"})
    g = g.sort_values("인원", ascending=True)
    fig = px.bar(
        g,
        x="인원",
        y="dept",
        orientation="h",
        labels={"dept": COL_LABELS["dept"], "인원": "인원"},
        height=max(320, 28 * len(g) + 80),
    )
    return fig


def fig_job_family_dist(filtered: pd.DataFrame) -> go.Figure:
    g = filtered.groupby("job_family", as_index=False).size().rename(columns={"size": "인원"})
    fig = px.pie(
        g,
        names="job_family",
        values="인원",
        hole=0.35,
        labels={"job_family": COL_LABELS["job_family"]},
        height=380,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return fig


def fig_employment_type(filtered: pd.DataFrame) -> go.Figure:
    g = (
        filtered.groupby("employment_type", as_index=False)
        .size()
        .rename(columns={"size": "인원"})
    )
    fig = px.bar(
        g,
        x="employment_type",
        y="인원",
        color="employment_type",
        labels={
            "employment_type": COL_LABELS["employment_type"],
            "인원": "인원",
        },
        height=360,
    )
    fig.update_layout(showlegend=False)
    return fig


def fig_hire_trend(filtered: pd.DataFrame) -> go.Figure:
    h = filtered.dropna(subset=["hire_month"])
    if h.empty:
        return go.Figure().update_layout(height=320, title="입사 데이터 없음")
    g = h.groupby("hire_month", as_index=False).size().rename(columns={"size": "입사자수"})
    fig = px.line(
        g,
        x="hire_month",
        y="입사자수",
        markers=True,
        labels={"hire_month": "입사월", "입사자수": "입사자 수"},
        height=360,
    )
    fig.update_traces(line=dict(width=2))
    return fig


def fig_tenure_hist(filtered: pd.DataFrame) -> go.Figure:
    return px.histogram(
        filtered,
        x="tenure_months",
        nbins=20,
        labels={"tenure_months": COL_LABELS["tenure_months"], "count": "인원"},
        height=360,
    )


def fig_status_by_division(filtered: pd.DataFrame) -> go.Figure:
    g = filtered.groupby(["division", "status"], as_index=False).size().rename(columns={"size": "인원"})
    fig = px.bar(
        g,
        x="division",
        y="인원",
        color="status",
        barmode="stack",
        labels={
            "division": COL_LABELS["division"],
            "status": COL_LABELS["status"],
            "인원": "인원",
        },
        height=380,
    )
    return fig
