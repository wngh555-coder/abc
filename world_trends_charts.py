"""
세계 트렌드 대시보드 시각화: 워드클라우드, Choropleth, 시계열.
"""

from __future__ import annotations

import io
import platform
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image

try:
    from wordcloud import WordCloud
except ImportError:  # pragma: no cover
    WordCloud = None  # type: ignore


def _korean_font_path() -> str | None:
    if platform.system() == "Windows":
        p = Path(r"C:\Windows\Fonts\malgun.ttf")
        if p.is_file():
            return str(p)
    if platform.system() == "Darwin":
        p = Path("/System/Library/Fonts/AppleSDGothicNeo.ttc")
        if p.is_file():
            return str(p)
    return None


def wordcloud_image(word_freq: dict[str, float], width: int = 900, height: int = 420) -> Image.Image | None:
    """키워드 가중치 dict → PIL Image. wordcloud 미설치 시 None."""
    if not word_freq or WordCloud is None:
        return None
    font = _korean_font_path()
    try:
        wc = WordCloud(
            width=width,
            height=height,
            background_color="white",
            font_path=font,
            max_words=80,
            relative_scaling=0.45,
            colormap="viridis",
        )
        wc.generate_from_frequencies({k: max(v, 0.01) for k, v in word_freq.items()})
        return wc.to_image()
    except Exception:
        wc = WordCloud(
            width=width,
            height=height,
            background_color="white",
            max_words=80,
            relative_scaling=0.45,
            colormap="viridis",
        )
        wc.generate_from_frequencies({k: max(v, 0.01) for k, v in word_freq.items()})
        return wc.to_image()


def wordcloud_png_bytes(word_freq: dict[str, float]) -> bytes | None:
    img = wordcloud_image(word_freq)
    if img is None:
        return None
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def fig_country_interest(country_df: pd.DataFrame) -> go.Figure:
    d = country_df.copy()
    fig = px.choropleth(
        d,
        locations="iso_alpha3",
        color="interest",
        locationmode="ISO-3",
        color_continuous_scale="Blues",
        hover_data={"country_ko": True, "interest": ":.1f", "iso_alpha3": False},
        labels={"interest": "관심도 지수", "country_ko": "국가"},
        height=480,
    )
    fig.update_geos(showframe=False, showcoastlines=True, projection_type="natural earth")
    fig.update_layout(margin=dict(l=0, r=0, t=30, b=0))
    return fig


def fig_timeline(timeline_df: pd.DataFrame) -> go.Figure:
    d = timeline_df.copy()
    if d.empty:
        return go.Figure()
    fig = px.area(
        d,
        x="time_utc",
        y="trend_score",
        labels={"time_utc": "시간 (UTC)", "trend_score": "트렌드 점수"},
        height=400,
    )
    fig.update_traces(line=dict(width=2))
    fig.update_layout(hovermode="x unified", margin=dict(l=0, r=0, t=30, b=0))
    return fig
