"""
타이타닉 데이터 탐색 대시보드 (Streamlit)
데이터: 프로젝트의 titanic.csv(우선) 또는 seaborn 온라인 데이터셋
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="타이타닉 대시보드",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def load_titanic() -> pd.DataFrame:
    csv_path = Path(__file__).resolve().parent / "titanic.csv"
    if csv_path.is_file():
        return pd.read_csv(csv_path)
    import seaborn as sns

    return sns.load_dataset("titanic")


df = load_titanic()
# 승선 항구 결측은 필터/집계에서 제외되지 않도록
df["embarked"] = df["embarked"].fillna("미상")

# 한글 컬럼 표시용 (원본은 영문 유지)
COL_LABELS = {
    "survived": "생존",
    "pclass": "객실 등급",
    "sex": "성별",
    "age": "나이",
    "sibsp": "형제·배우자",
    "parch": "부모·자녀",
    "fare": "운임",
    "embarked": "승선 항구",
    "class": "객실 등급(범주)",
    "who": "구분(남/여/아이)",
    "adult_male": "성인 남성",
    "deck": "갑판",
    "embark_town": "승선 도시",
    "alive": "생존 여부",
    "alone": "단독 승선",
}

st.title("🚢 타이타닉 데이터 대시보드")
st.caption("동일 스키마의 Titanic 데이터 · 사이드바에서 필터 후 차트와 표로 확인합니다.")

# --- 사이드바 필터 ---
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

mask = (
    df["sex"].isin(sex_opt)
    & df["pclass"].isin(class_opt)
    & df["embarked"].isin(embarked_opt)
    & df["age"].between(age_range[0], age_range[1])
)
filtered = df.loc[mask].copy()

# --- 상단 지표 ---
n_total = len(filtered)
n_surv = int(filtered["survived"].sum()) if n_total else 0
rate = (n_surv / n_total * 100) if n_total else 0.0

c1, c2, c3, c4 = st.columns(4)
c1.metric("표본 수", f"{n_total:,}")
c2.metric("생존자 수", f"{n_surv:,}")
c3.metric("생존률", f"{rate:.1f}%")
c4.metric("평균 운임", f"${filtered['fare'].mean():.2f}" if n_total else "—")

st.divider()

# --- 차트 영역 ---
left, right = st.columns(2)

with left:
    st.subheader("성별·객실 등급별 생존")
    if n_total:
        g = (
            filtered.groupby(["sex", "pclass"], as_index=False)["survived"]
            .mean()
            .rename(columns={"survived": "생존률"})
        )
        g["객실 등급"] = g["pclass"].astype(str) + "등급"
        fig_bar = px.bar(
            g,
            x="sex",
            y="생존률",
            color="객실 등급",
            barmode="group",
            labels={"sex": "성별", "생존률": "생존 비율"},
            height=380,
        )
        fig_bar.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")

with right:
    st.subheader("나이 분포 (생존 여부)")
    if n_total:
        _h = filtered.assign(
            생존여부=filtered["survived"].map({1: "생존", 0: "사망"})
        )
        fig_hist = px.histogram(
            _h,
            x="age",
            color="생존여부",
            nbins=30,
            opacity=0.75,
            labels={"age": "나이", "count": "인원"},
            color_discrete_map={"사망": "#c0392b", "생존": "#27ae60"},
            height=380,
        )
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")

row2_left, row2_right = st.columns(2)

with row2_left:
    st.subheader("승선 항구별 생존률")
    if n_total:
        emb = (
            filtered.groupby("embarked", as_index=False)["survived"]
            .mean()
            .rename(columns={"survived": "생존률", "embarked": "항구"})
        )
        fig_emb = px.bar(
            emb,
            x="항구",
            y="생존률",
            color="항구",
            height=360,
            labels={"생존률": "생존 비율"},
        )
        fig_emb.update_yaxes(tickformat=".0%")
        fig_emb.update_layout(showlegend=False)
        st.plotly_chart(fig_emb, use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")

with row2_right:
    st.subheader("운임 vs 나이 (객실 등급)")
    if n_total:
        _s = filtered.assign(
            생존여부=filtered["survived"].map({1: "생존", 0: "사망"})
        )
        fig_sc = px.scatter(
            _s,
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
        st.plotly_chart(fig_sc, use_container_width=True)
    else:
        st.info("조건에 맞는 데이터가 없습니다.")

st.subheader("상관 관계 (수치 변수)")
num_cols = ["survived", "pclass", "age", "sibsp", "parch", "fare"]
corr = filtered[num_cols].corr()
fig_heat = go.Figure(
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
)
fig_heat.update_layout(height=420)
st.plotly_chart(fig_heat, use_container_width=True)

st.subheader("필터 적용 데이터 미리보기")
st.dataframe(
    filtered.rename(columns=COL_LABELS),
    use_container_width=True,
    height=320,
)

with st.expander("데이터 출처 및 컬럼 설명"):
    st.markdown(
        """
        - **데이터**: 같은 폴더의 `titanic.csv`가 있으면 그걸 사용하고, 없으면 `seaborn.load_dataset("titanic")`으로 불러옵니다.
        - **survived**: 1 생존, 0 사망  
        - **pclass**: 1·2·3등급  
        - **embarked**: C(Cherbourg), Q(Queenstown), S(Southampton), 미상(원본 결측)
        """
    )
