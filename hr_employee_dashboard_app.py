"""
사내 직원 인사 통계 대시보드 (기획: docs/hr-employee-stats-dashboard-plan.md)

실행: streamlit run hr_employee_dashboard_app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from hr_employee_charts import (
    fig_employment_type,
    fig_headcount_by_dept,
    fig_hire_trend,
    fig_job_family_dist,
    fig_status_by_division,
    fig_tenure_hist,
)
from hr_employee_io import COL_LABELS, filter_hr_employees, kpi_from_filtered, load_hr_employees, prepare_hr_employees

st.set_page_config(
    page_title="인사 통계 대시보드",
    page_icon="👥",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def _cached_hr():
    return prepare_hr_employees(load_hr_employees())


df = _cached_hr()

snap = df["snapshot_date"].iloc[0] if len(df) else None
snap_s = snap.strftime("%Y-%m-%d") if snap is not None and pd.notna(snap) else "—"


st.title("👥 사내 인사 통계 대시보드")
st.caption(
    f"데이터 기준일(스냅샷): **{snap_s}** · 원천: `data/sample_hr_employees.csv` (없으면 내장 샘플). "
    "경영·인사 참고용이며, 지표 정의는 아래 Expander를 확인하세요."
)

with st.sidebar:
    st.header("필터")
    divisions = st.multiselect(
        "본부",
        options=sorted(df["division"].dropna().unique()),
        default=sorted(df["division"].dropna().unique()),
    )
    dept_opts = sorted(df.loc[df["division"].isin(divisions), "dept"].dropna().unique())
    depts = st.multiselect(
        "부서",
        options=dept_opts,
        default=dept_opts,
    )
    locations = st.multiselect(
        "지역",
        options=sorted(df["location"].dropna().unique()),
        default=sorted(df["location"].dropna().unique()),
    )
    job_families = st.multiselect(
        "직군",
        options=sorted(df["job_family"].dropna().unique()),
        default=sorted(df["job_family"].dropna().unique()),
    )
    grades = st.multiselect(
        "직급",
        options=sorted(df["grade"].dropna().unique()),
        default=sorted(df["grade"].dropna().unique()),
    )
    employment_types = st.multiselect(
        "고용형태",
        options=sorted(df["employment_type"].dropna().unique()),
        default=sorted(df["employment_type"].dropna().unique()),
    )
    statuses = st.multiselect(
        "재직상태",
        options=sorted(df["status"].dropna().unique()),
        default=sorted(df["status"].dropna().unique()),
    )
    t_min = float(df["tenure_months"].min()) if len(df) else 0.0
    t_max = float(df["tenure_months"].max()) if len(df) else 120.0
    tenure_range = st.slider(
        "근속(월) 범위",
        t_min,
        t_max,
        (t_min, t_max),
    )

filtered = filter_hr_employees(
    df,
    divisions=divisions,
    depts=depts,
    locations=locations,
    job_families=job_families,
    grades=grades,
    employment_types=employment_types,
    statuses=statuses,
    tenure_range=tenure_range,
)
kpi = kpi_from_filtered(filtered)

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("대상 인원", f"{kpi['n_total']:,}")
c2.metric("재직자", f"{kpi['n_active']:,}")
c3.metric("정규직 수", f"{kpi['n_regular']:,}")
c4.metric("정규직 비율", f"{kpi['regular_rate']:.1f}%")
c5.metric(
    "평균 근속(월)",
    f"{kpi['mean_tenure']:.1f}" if kpi["mean_tenure"] is not None else "—",
)
c6.metric("최근 12개월 입사", f"{kpi['hired_12m']:,}")

labeled = filtered.rename(columns=COL_LABELS)
csv_bytes = labeled.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "필터 결과 CSV",
    data=csv_bytes,
    file_name="hr_employees_filtered.csv",
    mime="text/csv",
    disabled=kpi["n_total"] == 0,
)

st.divider()

row1_l, row1_r = st.columns(2)
with row1_l:
    st.subheader("부서별 인원")
    if kpi["n_total"]:
        st.plotly_chart(fig_headcount_by_dept(filtered), use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")
with row1_r:
    st.subheader("직군 비중")
    if kpi["n_total"]:
        st.plotly_chart(fig_job_family_dist(filtered), use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")

row2_l, row2_r = st.columns(2)
with row2_l:
    st.subheader("고용형태별 인원")
    if kpi["n_total"]:
        st.plotly_chart(fig_employment_type(filtered), use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")
with row2_r:
    st.subheader("본부별 재직상태(스택)")
    if kpi["n_total"]:
        st.plotly_chart(fig_status_by_division(filtered), use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")

row3_l, row3_r = st.columns(2)
with row3_l:
    st.subheader("입사월별 입사자 수")
    if kpi["n_total"]:
        st.plotly_chart(fig_hire_trend(filtered), use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")
with row3_r:
    st.subheader("근속(월) 분포")
    if kpi["n_total"]:
        st.plotly_chart(fig_tenure_hist(filtered), use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")

st.subheader("필터 적용 데이터")
st.dataframe(labeled, use_container_width=True, height=360)

with st.expander("지표 정의 · 유의사항"):
    st.markdown(
        """
        - **대상 인원**: 사이드바 필터를 모두 적용한 행 수입니다.
        - **재직자**: `재직상태`가「재직」인 인원입니다.
        - **정규직 비율**: 정규직 인원 ÷ 대상 인원 × 100입니다.
        - **평균 근속(월)**: 스냅샷 기준일과 입사일 차이를 월 단위로 환산한 값의 평균입니다(약 30.44일/월).
        - **최근 12개월 입사**: 스냅샷일 기준 역산 12개월 이내 입사 인원입니다.
        - 실제 운영 시 휴직·퇴사자의 근속 정의, FTE 여부 등은 회사 정책에 맞게 조정하세요.
        - 본 화면은 **참고용**이며, 개인정보·민감정보는 최소화·권한 통제 원칙을 따릅니다.
        """
    )
