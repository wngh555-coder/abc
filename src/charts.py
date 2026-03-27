from __future__ import annotations

from typing import Iterable

import plotly.graph_objects as go

from .simulator import MatchResultDistribution
from .tactics import TeamIndices


def radar_tactical_indices(indices: TeamIndices, title: str = "팀 전술 프로파일") -> go.Figure:
    """
    Explainable 0~100-ish index radar.
    We intentionally avoid "pretty but opaque" scaling: axis values come directly from indices.
    """
    axes = [
        ("effective_attack", indices.effective_attack),
        ("effective_defense", indices.effective_defense),
        ("effective_midfield", indices.effective_midfield),
        ("effective_transition", indices.effective_transition),
        ("effective_stamina", indices.effective_stamina),
        ("volatility", indices.volatility),
    ]
    labels = [a[0].replace("effective_", "").replace("_", " ").title() for a in axes]
    values = [float(a[1]) for a in axes]

    fig = go.Figure(
        go.Scatterpolar(
            r=values + [values[0]],
            theta=labels + [labels[0]],
            fill="toself",
            mode="lines+markers",
            marker=dict(size=6),
            line=dict(width=2),
            name="Index",
        )
    )
    fig.update_layout(
        title=title,
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        margin=dict(l=25, r=25, t=60, b=20),
        height=420,
    )
    return fig


def tournament_path_bar(path_probs: dict[str, float], title: str = "토너먼트 진출 확률") -> go.Figure:
    # Map internal keys to Korean labels (requested UI)
    label_map = {
        "R32": "32강",
        "R16": "16강",
        "QF": "8강",
        "SF": "4강",
        "F": "결승",
        "W": "우승",
    }
    order = ["R32", "R16", "QF", "SF", "F", "W"]
    x = [label_map[k] for k in order]
    y = [float(path_probs.get(k, 0.0)) for k in order]

    fig = go.Figure(go.Bar(x=x, y=[round(p * 100, 2) for p in y], marker_color="#4C78A8"))
    fig.update_layout(
        title=title,
        yaxis=dict(title="확률(%)", range=[0, max(30, max(y) * 100 if y else 1)]),
        margin=dict(l=25, r=25, t=55, b=25),
        height=360,
    )
    return fig


def match_score_heatmap(dist: MatchResultDistribution, title: str = "예상 스코어 분포") -> go.Figure:
    """
    Heatmap for GF/GA probabilities for 0~5 goals.
    """
    max_goals = len(dist.score_matrix) - 1
    z = dist.score_matrix
    # Axis labels as strings are clearer in UI.
    tick = list(range(max_goals + 1))
    fig = go.Figure(
        go.Heatmap(
            x=tick,
            y=tick,
            z=[[z[gf][ga] for ga in tick] for gf in tick],
            colorscale="Blues",
            colorbar=dict(title="확률"),
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="상대 실점(GA)",
        yaxis_title="득점(GF)",
        margin=dict(l=30, r=30, t=55, b=30),
        height=420,
    )
    return fig

