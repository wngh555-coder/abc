"""
사내 직책자 프로파일링 대시보드 (Streamlit)
- 다면진단(360) + 인사평가 요약 · 추이 · 규칙 기반 내러티브

실행: streamlit run leader_profile_app.py
"""

from __future__ import annotations

import streamlit as st

from leader_profile_charts import (
    fig_gap_self_vs_others,
    fig_radar_latest,
    fig_rater_breakdown_small_multiples,
    fig_review_bands,
    fig_trend_others_by_dimension,
)
from leader_profile_io import (
    kpi_for_employee,
    load_leader_360,
    load_leader_master,
    load_leader_reviews,
    narrative_bullets,
    slice_360,
    slice_reviews,
)

st.set_page_config(
    page_title="직책자 프로파일",
    page_icon="👤",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def _cached_master():
    return load_leader_master()


@st.cache_data
def _cached_360():
    return load_leader_360()


@st.cache_data
def _cached_reviews():
    return load_leader_reviews()


master = _cached_master()
df_360 = _cached_360()
df_rev = _cached_reviews()

st.title("직책자 프로파일 대시보드")
st.caption(
    "다면진단·인사평가 데이터를 한 화면에서 묶어 **성향·역량 추이**를 빠르게 파악합니다. "
    "자동 문구는 **참고용**이며, 인사 의사결정의 근거는 내부 규정·면담·원본 기록을 따릅니다."
)

if master.empty:
    st.error("`data/sample_leader_master.csv`를 찾을 수 없습니다.")
    st.stop()

opts = master.apply(lambda r: f"{r['display_label']} [{r['employee_ref']}]", axis=1).tolist()
ref_by_label = {f"{r['display_label']} [{r['employee_ref']}]": r["employee_ref"] for _, r in master.iterrows()}

with st.sidebar:
    st.header("대상 선택")
    choice = st.selectbox("직책자", options=opts, index=0)
    employee_ref = ref_by_label[choice]
    row = master[master["employee_ref"] == employee_ref].iloc[0]
    st.divider()
    st.markdown(f"**직책** {row.get('role_title', '—')}")
    st.markdown(f"**직책 기준 근속(월)** {int(row['tenure_months_in_role'])}")
    st.caption("데모 데이터는 가명·가공입니다. 실제 연동 시 HRIS/평가 시스템 스키마에 맞게 매핑하세요.")

emp_360 = slice_360(df_360, employee_ref)
emp_rev = slice_reviews(df_rev, employee_ref)
kpi = kpi_for_employee(df_360, df_rev, employee_ref)

c1, c2, c3, c4 = st.columns(4)
c1.metric("최근 다면 회차", kpi["latest_360_year"] if kpi["latest_360_year"] else "—")
c2.metric("최근 타 평가자 평균", f"{kpi['others_mean_latest']:.2f}" if kpi["others_mean_latest"] else "—")
c3.metric("최근 본인 평균", f"{kpi['self_mean_latest']:.2f}" if kpi["self_mean_latest"] else "—")
c4.metric(
    "최신 평가 등급",
    f"{kpi['latest_rating_band']} ({kpi['latest_review_year']})"
    if kpi["latest_rating_band"] and kpi["latest_review_year"]
    else "—",
)

st.subheader("이 사람은 어떤 사람일까? — 한눈에 요약")
for line in narrative_bullets(df_360, df_rev, employee_ref):
    st.markdown(f"- {line}")

st.divider()

tab_a, tab_b, tab_c, tab_d = st.tabs(["다면진단 · 최근 패턴", "연도별 추이", "인사평가", "원본 데이터"])

with tab_a:
    if kpi["latest_360_year"] is None or emp_360.empty:
        st.info("다면진단 데이터가 없습니다.")
    else:
        y = int(kpi["latest_360_year"])
        r1, r2 = st.columns(2)
        with r1:
            st.plotly_chart(fig_radar_latest(emp_360, y), use_container_width=True)
        with r2:
            st.plotly_chart(fig_gap_self_vs_others(emp_360, y), use_container_width=True)
        st.plotly_chart(fig_rater_breakdown_small_multiples(emp_360, y), use_container_width=True)

with tab_b:
    if emp_360.empty:
        st.info("다면진단 데이터가 없습니다.")
    else:
        st.plotly_chart(fig_trend_others_by_dimension(emp_360), use_container_width=True)

with tab_c:
    if emp_rev.empty:
        st.info("인사평가 데이터가 없습니다.")
    else:
        st.plotly_chart(fig_review_bands(emp_rev), use_container_width=True)
        st.subheader("연도별 코멘트 요약")
        for _, r in emp_rev.sort_values("year").iterrows():
            with st.expander(f"{int(r['year'])}년 — 등급 {r['rating_band']}"):
                st.markdown(f"**강점** {r['strengths']}")
                st.markdown(f"**개발 과제** {r['development_focus']}")
                st.markdown(f"**한 줄** {r['comment_short']}")

with tab_d:
    st.dataframe(emp_360, use_container_width=True, height=280)
    st.dataframe(emp_rev, use_container_width=True, height=220)

with st.expander("데이터 파일·컬럼 정의"):
    st.markdown(
        """
        - `data/sample_leader_master.csv`: 표시용 라벨, 직책, 직책 근속(월)
        - `data/sample_leader_360.csv`: `employee_ref`, `cycle_year`, `dimension`, `rater_type`(self/manager/peer/direct), `score`
        - `data/sample_leader_reviews.csv`: `year`, `rating_band`, `strengths`, `development_focus`, `comment_short`
        - 실제 도입 시 개인정보·열람 권한·로그 정책을 반드시 적용하세요.
        """
    )
