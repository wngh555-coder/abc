"""
기획서(docs/streamlit-dashboard-plan.md) 기반 타이타닉 데이터 대시보드 진입점.

실행: streamlit run dashboard_app.py
"""

import streamlit as st

from dashboard_charts import (
    fig_age_survival_hist,
    fig_embarked_survival,
    fig_fare_age_scatter,
    fig_numeric_corr,
    fig_survival_by_sex_class,
)
from dashboard_io import COL_LABELS, filter_titanic, kpi_from_filtered, load_titanic, prepare_titanic

st.set_page_config(
    page_title="타이타닉 대시보드",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def _cached_titanic():
    return prepare_titanic(load_titanic())


df = _cached_titanic()

st.title("🚢 타이타닉 데이터 대시보드")
st.caption(
    "동일 스키마의 Titanic 데이터 · 사이드바에서 필터 후 차트와 표로 확인합니다. "
    "데이터는 로컬 `titanic.csv` 우선, 없으면 seaborn 샘플을 사용합니다."
)

with st.sidebar:
    st.header("필터")
    sex_opt = st.multiselect(
        "성별",
        options=sorted(df["sex"].dropna().unique()),
        default=list(df["sex"].dropna().unique()),
    )
    class_opt = st.multiselect(
        "객실 등급",
        options=sorted(df["pclass"].dropna().unique()),
        default=list(df["pclass"].dropna().unique()),
    )
    embarked_vals = df["embarked"].dropna().unique().tolist()
    embarked_opt = st.multiselect(
        "승선 항구",
        options=sorted(embarked_vals),
        default=sorted(embarked_vals),
    )
    age_range = st.slider(
        "나이 범위",
        float(df["age"].min()),
        float(df["age"].max()),
        (float(df["age"].min()), float(df["age"].max())),
    )

filtered = filter_titanic(
    df,
    sex_opt=sex_opt,
    class_opt=class_opt,
    embarked_opt=embarked_opt,
    age_range=age_range,
)
kpi = kpi_from_filtered(filtered)

c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])
c1.metric("표본 수", f"{kpi['n_total']:,}")
c2.metric("생존자 수", f"{kpi['n_surv']:,}")
c3.metric("생존률", f"{kpi['rate']:.1f}%")
c4.metric("평균 운임", f"${kpi['mean_fare']:.2f}" if kpi["mean_fare"] is not None else "—")
labeled = filtered.rename(columns=COL_LABELS)
csv_bytes = labeled.to_csv(index=False).encode("utf-8-sig")
c5.download_button(
    "필터 결과 CSV",
    data=csv_bytes,
    file_name="titanic_filtered.csv",
    mime="text/csv",
    disabled=kpi["n_total"] == 0,
)

st.divider()

left, right = st.columns(2)
with left:
    st.subheader("성별·객실 등급별 생존")
    if kpi["n_total"]:
        st.plotly_chart(fig_survival_by_sex_class(filtered), use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")

with right:
    st.subheader("나이 분포 (생존 여부)")
    if kpi["n_total"]:
        st.plotly_chart(fig_age_survival_hist(filtered), use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")

row2_left, row2_right = st.columns(2)
with row2_left:
    st.subheader("승선 항구별 생존률")
    if kpi["n_total"]:
        st.plotly_chart(fig_embarked_survival(filtered), use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")

with row2_right:
    st.subheader("운임 vs 나이 (객실 등급)")
    if kpi["n_total"]:
        st.plotly_chart(fig_fare_age_scatter(filtered), use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")

st.subheader("상관 관계 (수치 변수)")
if kpi["n_total"]:
    st.plotly_chart(fig_numeric_corr(filtered), use_container_width=True)
else:
    st.info("조건에 맞는 데이터가 없습니다.")

st.subheader("필터 적용 데이터 미리보기")
st.dataframe(labeled, use_container_width=True, height=320)

with st.expander("데이터 출처 및 컬럼 설명"):
    st.markdown(
        """
        - **데이터**: 같은 폴더의 `titanic.csv`가 있으면 그걸 사용하고, 없으면 `seaborn.load_dataset("titanic")`으로 불러옵니다.
        - **survived**: 1 생존, 0 사망
        - **pclass**: 1·2·3등급
        - **embarked**: C(Cherbourg), Q(Queenstown), S(Southampton), 미상(원본 결측)
        """
    )
