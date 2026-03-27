"""
사내 직책자 프로파일링 대시보드 (단일 파일)
- 다면진단(360) + 인사평가 요약 · 추이 · 규칙 기반 내러티브

실행: streamlit run leader_profile_dashboard.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ---------------------------------------------------------------------------
# 데이터 · 집계
# ---------------------------------------------------------------------------

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"

RATER_LABELS_KR = {
    "self": "본인",
    "manager": "상위",
    "peer": "동료",
    "direct": "하위",
}


def load_leader_master() -> pd.DataFrame:
    p = DATA / "sample_leader_master.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, encoding="utf-8-sig")


def load_leader_360() -> pd.DataFrame:
    p = DATA / "sample_leader_360.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, encoding="utf-8-sig")
    if "cycle_year" in df.columns:
        df["cycle_year"] = df["cycle_year"].astype(int)
    return df


def load_leader_reviews() -> pd.DataFrame:
    p = DATA / "sample_leader_reviews.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, encoding="utf-8-sig")
    if "year" in df.columns:
        df["year"] = df["year"].astype(int)
    return df


def slice_360(df: pd.DataFrame, employee_ref: str) -> pd.DataFrame:
    if df.empty or "employee_ref" not in df.columns:
        return df.iloc[0:0].copy()
    return df[df["employee_ref"] == employee_ref].copy()


def slice_reviews(df: pd.DataFrame, employee_ref: str) -> pd.DataFrame:
    if df.empty or "employee_ref" not in df.columns:
        return df.iloc[0:0].copy()
    return df[df["employee_ref"] == employee_ref].copy()


def latest_cycle_year(df_360: pd.DataFrame) -> int | None:
    if df_360.empty or "cycle_year" not in df_360.columns:
        return None
    return int(df_360["cycle_year"].max())


def others_only(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["rater_type"] != "self"].copy()


def kpi_for_employee(
    df_360: pd.DataFrame,
    df_rev: pd.DataFrame,
    employee_ref: str,
) -> dict:
    s360 = slice_360(df_360, employee_ref)
    srev = slice_reviews(df_rev, employee_ref)
    yr = latest_cycle_year(s360)
    others_mean = None
    self_mean = None
    if yr is not None and not s360.empty:
        last = s360[s360["cycle_year"] == yr]
        o = others_only(last)
        if not o.empty:
            others_mean = float(o["score"].mean())
        slf = last[last["rater_type"] == "self"]
        if not slf.empty:
            self_mean = float(slf["score"].mean())
    latest_band = None
    latest_year_rev = None
    if not srev.empty:
        srev = srev.sort_values("year")
        last_r = srev.iloc[-1]
        latest_band = str(last_r["rating_band"])
        latest_year_rev = int(last_r["year"])
    return {
        "latest_360_year": yr,
        "others_mean_latest": others_mean,
        "self_mean_latest": self_mean,
        "latest_rating_band": latest_band,
        "latest_review_year": latest_year_rev,
    }


def narrative_bullets(
    df_360: pd.DataFrame,
    df_rev: pd.DataFrame,
    employee_ref: str,
    gap_threshold: float = 0.22,
    trend_threshold: float = 0.12,
) -> list[str]:
    out: list[str] = []
    s360 = slice_360(df_360, employee_ref)
    srev = slice_reviews(df_rev, employee_ref)
    if s360.empty:
        return ["다면진단 데이터가 없습니다."]

    yr = latest_cycle_year(s360)
    if yr is None:
        return ["다면진단 연도를 확인할 수 없습니다."]

    last = s360[s360["cycle_year"] == yr]
    by_dim = []
    for dim, g in last.groupby("dimension"):
        slf = g[g["rater_type"] == "self"]["score"].mean()
        oth = g[g["rater_type"] != "self"]["score"].mean()
        if pd.notna(slf) and pd.notna(oth):
            by_dim.append((dim, float(slf), float(oth)))
    hi_self = [(d, slf - oth) for d, slf, oth in by_dim if slf - oth >= gap_threshold]
    lo_self = [(d, oth - slf) for d, slf, oth in by_dim if oth - slf >= gap_threshold]
    if hi_self:
        hi_self.sort(key=lambda x: -x[1])
        out.append(
            f"최근 회차({yr})에서 본인 점수가 타 평가자 평균보다 높은 영역: "
            + ", ".join(d for d, _ in hi_self[:3])
            + " — 자기인식과 타인 인식 차이를 면담에서 확인해 보는 것이 좋습니다."
        )
    if lo_self:
        lo_self.sort(key=lambda x: -x[1])
        out.append(
            f"타 평가자 평균이 본인보다 높게 나온 영역: "
            + ", ".join(d for d, _ in lo_self[:3])
            + " — 강점으로 작동 중일 수 있으나 본인은 과소평가하는 패턴일 수 있습니다."
        )

    o_all = others_only(s360)
    if not o_all.empty:
        ymean = o_all.groupby("cycle_year")["score"].mean()
        if len(ymean) >= 2:
            first_y = int(ymean.index.min())
            last_y = int(ymean.index.max())
            delta = float(ymean.loc[last_y] - ymean.loc[first_y])
            if delta >= trend_threshold:
                out.append(
                    f"{first_y}~{last_y} 동안 타 평가자 기준 평균 점수가 약 {delta:+.2f} 상승한 추세입니다."
                )
            elif delta <= -trend_threshold:
                out.append(
                    f"{first_y}~{last_y} 동안 타 평가자 기준 평균 점수가 약 {delta:+.2f} 하락한 추세입니다. 맥락(조직 변화·과제 난이도)을 함께 봅니다."
                )

    o_last = others_only(last)
    if not o_last.empty:
        dim_mean = o_last.groupby("dimension")["score"].mean().sort_values(ascending=False)
        top = dim_mean.head(2).index.tolist()
        bot = dim_mean.tail(2).index.tolist()
        out.append("최근 타 평가자 기준 상대적으로 높은 역량: " + ", ".join(top) + ".")
        out.append("상대적으로 낮게 나온 역량(개발 대화 시 참고): " + ", ".join(bot) + ".")

    if not srev.empty:
        srev = srev.sort_values("year")
        r = srev.iloc[-1]
        out.append(
            f"{int(r['year'])} 인사평가 등급은 **{r['rating_band']}**입니다. "
            f"강점 요약: {r['strengths']}"
        )

    return out if out else ["요약 규칙에 해당하는 문장이 없습니다. 원본 지표를 확인하세요."]


# ---------------------------------------------------------------------------
# 차트
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

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
