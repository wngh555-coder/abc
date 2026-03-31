"""
대시보드용 Plotly 차트 빌더 (필터 적용된 DataFrame 입력)
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dashboard_io import COL_LABELS


def fig_survival_by_sex_class(filtered: pd.DataFrame) -> go.Figure:
    g = (
        filtered.groupby(["sex", "pclass"], as_index=False)["survived"]
        .mean()
        .rename(columns={"survived": "생존률"})
    )
    g["객실 등급"] = g["pclass"].astype(str) + "등급"
    fig = px.bar(
        g,
        x="sex",
        y="생존률",
        color="객실 등급",
        barmode="group",
        labels={"sex": "성별", "생존률": "생존 비율"},
        height=380,
    )
    fig.update_yaxes(tickformat=".0%")
    return fig


def fig_age_survival_hist(filtered: pd.DataFrame) -> go.Figure:
    h = filtered.assign(생존여부=filtered["survived"].map({1: "생존", 0: "사망"}))
    return px.histogram(
        h,
        x="age",
        color="생존여부",
        nbins=30,
        opacity=0.75,
        labels={"age": "나이", "count": "인원"},
        color_discrete_map={"사망": "#c0392b", "생존": "#27ae60"},
        height=380,
    )


def fig_embarked_survival(filtered: pd.DataFrame) -> go.Figure:
    emb = (
        filtered.groupby("embarked", as_index=False)["survived"]
        .mean()
        .rename(columns={"survived": "생존률", "embarked": "항구"})
    )
    fig = px.bar(
        emb,
        x="항구",
        y="생존률",
        color="항구",
        height=360,
        labels={"생존률": "생존 비율"},
    )
    fig.update_yaxes(tickformat=".0%")
    fig.update_layout(showlegend=False)
    return fig


def fig_fare_age_scatter(filtered: pd.DataFrame) -> go.Figure:
    s = filtered.assign(생존여부=filtered["survived"].map({1: "생존", 0: "사망"}))
    return px.scatter(
        s,
        x="age",
        y="fare",
        color="pclass",
        symbol="생존여부",
        height=360,
        labels={
            "age": "나이",
            "fare": "운임 ($)",
            "pclass": "객실 등급",
        },
        opacity=0.65,
    )


def fig_numeric_corr(filtered: pd.DataFrame) -> go.Figure:
    num_cols = ["survived", "pclass", "age", "sibsp", "parch", "fare"]
    corr = filtered[num_cols].corr()
    return go.Figure(
        data=go.Heatmap(
            z=corr.values,
            x=[COL_LABELS.get(c, c) for c in corr.columns],
            y=[COL_LABELS.get(c, c) for c in corr.index],
            colorscale="RdBu_r",
            zmid=0,
            text=[[f"{v:.2f}" for v in row] for row in corr.values],
            texttemplate="%{text}",
            textfont={"size": 11},
        )
    ).update_layout(height=420)
