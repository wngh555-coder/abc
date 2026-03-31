"""
세계 트렌드 실시간 탐지기 — Streamlit 진입점.

실행: streamlit run world_trends_app.py
"""

from __future__ import annotations

import time

import streamlit as st

from world_trends_charts import (
    fig_country_interest,
    fig_timeline,
    wordcloud_image,
)
from world_trends_io import list_topic_ids, simulate_trends

st.set_page_config(
    page_title="세계 트렌드 실시간 탐지기",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

TOPICS = list_topic_ids()


@st.cache_data(ttl=120)
def _cached_snapshot(seed: int, topic_id: str, hours: int):
    return simulate_trends(seed=seed, topic_id=topic_id, hours=hours)


st.title("🌍 세계 트렌드 실시간 탐지기")
st.caption(
    "뉴스·소셜 키워드 스타일의 **데모 시뮬레이션**입니다. "
    "운영 환경에서는 동일 화면에 뉴스/RSS·X API 등을 연동할 수 있습니다."
)

if "trend_seed" not in st.session_state:
    st.session_state.trend_seed = int(time.time()) % 100_000

with st.sidebar:
    st.header("탐지 설정")
    topic = st.selectbox("주제 프리셋", options=TOPICS, index=0)
    hours = st.slider("분석 기간 (시간)", min_value=12, max_value=168, value=48, step=12)
    if st.button("🔄 스냅샷 새로고침", help="시드를 바꿔 최신 유사 트렌드를 다시 생성합니다."):
        st.session_state.trend_seed = int(time.time()) % 1_000_000
    st.caption("캐시 TTL 120초 — 같은 설정은 잠시 동안 동일 스냅샷이 재사용될 수 있습니다.")

snap = _cached_snapshot(st.session_state.trend_seed, topic, hours)

c1, c2, c3 = st.columns(3)
c1.metric("추적 키워드 수", f"{len(snap.word_freq):,}")
peak_time = snap.timeline_df.loc[snap.timeline_df["trend_score"].idxmax(), "time_utc"]
c2.metric("피크 시각 (UTC)", peak_time.strftime("%m-%d %H:%M"))
top_row = snap.country_df.sort_values("interest", ascending=False).iloc[0]
c3.metric("관심도 1위 국가", f"{top_row['country_ko']} ({top_row['interest']:.0f})")

st.divider()

wc_img = wordcloud_image(snap.word_freq)
col_left, col_right = st.columns([1.1, 1.0], gap="large")

with col_left:
    st.subheader("핫 키워드 — 워드클라우드")
    if wc_img is not None:
        st.image(wc_img, use_container_width=True)
    else:
        st.warning("`wordcloud` 패키지를 설치하면 워드클라우드가 표시됩니다. `pip install wordcloud`")

with col_right:
    st.subheader("국가별 관심도")
    st.plotly_chart(fig_country_interest(snap.country_df), use_container_width=True)

st.subheader("시간별 트렌드 변화 (합성 점수)")
st.plotly_chart(fig_timeline(snap.timeline_df), use_container_width=True)

with st.expander("키워드 가중치 (상위 15개)"):
    items = sorted(snap.word_freq.items(), key=lambda x: x[1], reverse=True)[:15]
    for w, v in items:
        st.write(f"- **{w}** — {v:.2f}")

st.caption(
    f"주제: {snap.label_topic} · 생성(UTC): {snap.generated_at.strftime('%Y-%m-%d %H:%M:%S')}"
)
