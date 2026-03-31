"""
================================================================================
직책자 프로파일링 대시보드 — 기획 요약 (데이터 연계)
================================================================================

[목적]
  다면진단(서술) · 성과평가 · 성격평가 · HR 세션(면담) 정보를 한 직책자 단위로
  묶어, 연도 맥락 속에서 “어떤 사람인지” 빠르게 읽을 수 있게 한다.

[데이터 소스 → 화면 매핑]
  1) 다면진단(서술형, 연 1회)
     - 동료(peer) / 산하직원(direct_report), rater_seq 1~10까지 확장 가능.
     - 화면: 연도·평가자 유형 필터, 카드/Expander로 강점·보완점 원문 열람.
     - 집계: 연도별 응답 수, 유형별 응답 수 KPI.

  2) 성과평가(연말 등급 + 1차/2차 종합 의견)
     - 등급: S / A / B+ / B / C / D.
     - 화면: 등급 추이(시계열), 연도별 상세에서 1차·2차 의견 병기(비교 읽기).

  3) 성격평가(상위직책자, 연 최대 5개 태그)
     - 롱 포맷: (year, trait_order, trait_label).
     - 화면: 연도별 뱃지(태그) 나열, 누적 빈도 막대(여러 해에 반복된 성격 키워드).

  4) 세션정보(HR·직책자 면담, 1차/2차 서술)
     - 회차명(session_name) + 연도.
     - 화면: 타임라인식 목록, 1차/2차 코멘트 분리 표시.

[정보 구조(IA)]
  사이드바: 대상 직책자, (선택) 연도 범위
  탭: 한눈에 요약 | 성과평가 | 다면진단 | 성격평가 | 세션정보 | 데이터 정의

[준법·운영]
  - 자동 생성 요약 문구는 참고용. 인사 의사결정·면담 설계는 규정·원문 기준.
  - 실제 연동 시 열람 권한·로그·비식별 정책을 반드시 적용.

실행: python -m streamlit run leader_profiling_dashboard.py
================================================================================
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# 경로 · 상수
# ---------------------------------------------------------------------------

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"

GRADE_ORDER = ["D", "C", "B", "B+", "A", "S"]
GRADE_TO_Y = {g: i for i, g in enumerate(GRADE_ORDER)}

RATER_LABELS = {"peer": "동료", "direct_report": "산하직원"}

# (구문, 기본 가중, 카테고리) — 긴 구문을 우선 매칭하기 위해 길이 역순으로 스캔
LEXICON: list[tuple[str, float, str]] = [
    ("재발 방지", 3.6, "risk"),
    ("일정 관리", 2.4, "develop"),
    ("심리 안전", 2.9, "strength"),
    ("번아웃", 3.5, "risk"),
    ("스트레스", 3.0, "risk"),
    ("다소 소극적", 2.6, "develop"),
    ("매우 적극적", 2.3, "strength"),
    ("파이프라인", 2.1, "develop"),
    ("피드백", 2.6, "develop"),
    ("온보딩", 2.1, "develop"),
    ("우선순위", 2.2, "neutral"),
    ("이해관계자", 2.0, "neutral"),
    ("크로스펑셔널", 2.0, "neutral"),
    ("갈등", 3.0, "develop"),
    ("협업", 2.6, "develop"),
    ("소통", 2.6, "develop"),
    ("실행", 2.3, "strength"),
    ("전략", 2.2, "strength"),
    ("리더십", 2.1, "strength"),
    ("육성", 2.4, "develop"),
    ("승계", 2.4, "develop"),
    ("코칭", 2.3, "strength"),
    ("디테일", 2.1, "develop"),
    ("신뢰", 2.5, "strength"),
    ("성과", 2.0, "neutral"),
    ("개편", 1.9, "neutral"),
    ("직설적", 2.0, "develop"),
    ("규범 준수", 2.0, "neutral"),
    ("이타적", 2.2, "strength"),
    ("신중함", 2.0, "neutral"),
    ("개방적", 2.0, "strength"),
    ("책임감", 2.3, "strength"),
]

# 카테고리 표시 우선순위 (경중): 리스크·보완을 먼저, 그다음 강점
CAT_ORDER = {"risk": 0, "develop": 1, "personality": 2, "strength": 3, "neutral": 4}

# 출처별 가중: 2차·상위 판단이 반영된 기록에 더 큰 비중
SRC_WEIGHT = {
    "eval_secondary": 1.45,
    "eval_primary": 1.05,
    "session_secondary": 1.35,
    "session_primary": 1.0,
    "360_improve_peer": 0.95,
    "360_improve_dr": 1.1,
    "360_strength_peer": 0.85,
    "360_strength_dr": 0.95,
}


def _read_csv(name: str) -> pd.DataFrame:
    p = DATA / name
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, encoding="utf-8-sig")


def load_master() -> pd.DataFrame:
    return _read_csv("sample_executive_master.csv")


def load_performance() -> pd.DataFrame:
    df = _read_csv("sample_executive_performance.csv")
    if not df.empty and "year" in df.columns:
        df["year"] = df["year"].astype(int)
    return df


def load_360_narrative() -> pd.DataFrame:
    df = _read_csv("sample_executive_360_narrative.csv")
    if not df.empty:
        df["year"] = df["year"].astype(int)
    return df


def load_personality() -> pd.DataFrame:
    df = _read_csv("sample_executive_personality.csv")
    if not df.empty:
        df["year"] = df["year"].astype(int)
    return df


def load_sessions() -> pd.DataFrame:
    df = _read_csv("sample_executive_sessions.csv")
    if not df.empty:
        df["year"] = df["year"].astype(int)
    return df


def slice_emp(df: pd.DataFrame, ref: str) -> pd.DataFrame:
    if df.empty or "employee_ref" not in df.columns:
        return df.iloc[0:0].copy()
    return df[df["employee_ref"] == ref].copy()


def fig_grade_timeline(df_perf: pd.DataFrame) -> go.Figure:
    if df_perf.empty:
        return go.Figure(layout=dict(title="성과평가 데이터 없음", height=320))
    t = df_perf.sort_values("year")
    ys = [GRADE_TO_Y.get(str(g), 2) for g in t["grade"]]
    fig = go.Figure(
        go.Scatter(
            x=t["year"],
            y=ys,
            mode="lines+markers+text",
            text=t["grade"],
            textposition="top center",
            line=dict(width=2, color="#636EFA"),
            marker=dict(size=11),
        )
    )
    fig.update_layout(
        title="성과평가 등급 추이",
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(GRADE_ORDER))),
            ticktext=GRADE_ORDER,
            range=[-0.5, len(GRADE_ORDER) - 0.5],
        ),
        xaxis=dict(dtick=1),
        height=380,
        margin=dict(t=48, b=40),
    )
    return fig


def fig_trait_frequency(df_pers: pd.DataFrame) -> go.Figure:
    if df_pers.empty:
        return go.Figure(layout=dict(title="성격평가 데이터 없음", height=320))
    cnt = Counter(df_pers["trait_label"].astype(str))
    labels = [k for k, _ in cnt.most_common(12)]
    vals = [cnt[k] for k in labels]
    fig = go.Figure(go.Bar(x=vals, y=labels, orientation="h", marker_color="#00CC96"))
    fig.update_layout(
        title="성격 태그 누적 빈도 (선택 인원·전체 연도)",
        xaxis_title="출현 횟수",
        yaxis_title="",
        height=max(320, 40 + len(labels) * 28),
        margin=dict(l=160, t=48, b=40),
    )
    return fig


def _filter_year(df: pd.DataFrame, yr_lo: int, yr_hi: int) -> pd.DataFrame:
    if df.empty or "year" not in df.columns:
        return df
    return df[(df["year"] >= yr_lo) & (df["year"] <= yr_hi)].copy()


def _safe_int(y) -> int:
    try:
        return int(y)
    except (TypeError, ValueError):
        return int(float(y))


def _recency_multiplier(year: int, y_max: int, y_min: int) -> float:
    """필터 구간 내 최신 연도에 더 큰 가중."""
    span = max(y_max - y_min, 0)
    if span <= 0:
        return 1.35
    t = (year - y_min) / span
    return 1.0 + 0.3 * t


def _match_lexicon(text: str, lex_sorted: list[tuple[str, float, str]]) -> list[tuple[str, float, str]]:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return []
    t = str(text).strip()
    if not t:
        return []
    hits: list[tuple[str, float, str]] = []
    used_spans: list[tuple[int, int]] = []

    def overlaps(a: int, b: int) -> bool:
        for u, v in used_spans:
            if not (b <= u or a >= v):
                return True
        return False

    for phrase, w, cat in lex_sorted:
        start = 0
        while True:
            j = t.find(phrase, start)
            if j < 0:
                break
            end = j + len(phrase)
            if not overlaps(j, end):
                hits.append((phrase, w, cat))
                used_spans.append((j, end))
            start = j + 1
    return hits


def _lex_sorted():
    return sorted(LEXICON, key=lambda x: -len(x[0]))


def build_prioritized_summary(
    ref: str,
    df_perf: pd.DataFrame,
    df_360: pd.DataFrame,
    df_pers: pd.DataFrame,
    df_sess: pd.DataFrame,
    yr_lo: int,
    yr_hi: int,
) -> dict:
    """
    출처·서열·최신성 가중을 반영한 요약.
    - 성과: 2차 의견 > 1차, 필터 구간의 최신 연도에 가중.
    - 세션: 2차 > 1차.
    - 다면: 보완점 > 강점(관찰 경중), 산하 > 동료(현장 근접 가정).
    - 성격: trait_order 1~5 (상위직이 앞에 둔 태그일수록 가중).
    """
    lex = _lex_sorted()
    scored: Counter[tuple[str, str]] = Counter()

    def add_hits(text, base_src: float, year: int, y_min: int, y_max: int):
        rm = _recency_multiplier(year, y_max, y_min)
        for phrase, w, cat in _match_lexicon(text, lex):
            scored[(phrase, cat)] += w * base_src * rm

    p = _filter_year(slice_emp(df_perf, ref), yr_lo, yr_hi)
    s360 = _filter_year(slice_emp(df_360, ref), yr_lo, yr_hi)
    pers = _filter_year(slice_emp(df_pers, ref), yr_lo, yr_hi)
    sess = _filter_year(slice_emp(df_sess, ref), yr_lo, yr_hi)

    years_union = []
    for d in (p, s360, pers, sess):
        if not d.empty and "year" in d.columns:
            years_union.extend(d["year"].tolist())
    y_min_f = min(years_union) if years_union else yr_lo
    y_max_f = max(years_union) if years_union else yr_hi

    for _, r in p.iterrows():
        y = _safe_int(r["year"])
        add_hits(r.get("opinion_primary"), SRC_WEIGHT["eval_primary"], y, y_min_f, y_max_f)
        add_hits(r.get("opinion_secondary"), SRC_WEIGHT["eval_secondary"], y, y_min_f, y_max_f)

    for _, r in sess.iterrows():
        y = _safe_int(r["year"])
        add_hits(r.get("opinion_primary"), SRC_WEIGHT["session_primary"], y, y_min_f, y_max_f)
        add_hits(r.get("opinion_secondary"), SRC_WEIGHT["session_secondary"], y, y_min_f, y_max_f)

    for _, r in s360.iterrows():
        y = _safe_int(r["year"])
        rt = str(r.get("rater_type", ""))
        is_dr = rt == "direct_report"
        w_imp = SRC_WEIGHT["360_improve_dr"] if is_dr else SRC_WEIGHT["360_improve_peer"]
        w_str = SRC_WEIGHT["360_strength_dr"] if is_dr else SRC_WEIGHT["360_strength_peer"]
        add_hits(r.get("improvement_text"), w_imp, y, y_min_f, y_max_f)
        add_hits(r.get("strength_text"), w_str, y, y_min_f, y_max_f)

    for _, r in pers.iterrows():
        y = _safe_int(r["year"])
        order = int(r.get("trait_order", 3))
        order_mult = max(0.55, 1.55 - 0.2 * (order - 1))
        rm = _recency_multiplier(y, y_max_f, y_min_f)
        lab = str(r.get("trait_label", "")).strip()
        if lab:
            scored[(lab, "personality")] += 2.8 * order_mult * rm

    lines_perf: list[str] = []
    if not p.empty:
        p = p.sort_values("year")
        g0, g1 = str(p.iloc[0]["grade"]), str(p.iloc[-1]["grade"])
        y0, y1 = _safe_int(p.iloc[0]["year"]), _safe_int(p.iloc[-1]["year"])
        if y0 != y1:
            lines_perf.append(f"{y0}~{y1} 성과평가 등급: **{g0}** → **{g1}** (필터 구간 기준).")
        else:
            lines_perf.append(f"{y1} 성과평가 등급: **{g1}** (필터 구간 기준).")

    kw_lines: list[str] = []
    if scored:
        ranked = sorted(
            scored.items(),
            key=lambda it: (-it[1], CAT_ORDER.get(it[0][1], 9), it[0][0]),
        )
        top = ranked[:8]
        cat_kr = {
            "risk": "리스크·주의",
            "develop": "보완·개발",
            "strength": "강점",
            "personality": "성격태그",
            "neutral": "기타 맥락",
        }
        for (phrase, cat), val in top:
            tag = cat_kr.get(cat, cat)
            kw_lines.append(f"**{phrase}** — {tag} (가중합 약 {val:.1f})")

    lines_meta: list[str] = []
    if not s360.empty:
        ly = int(s360["year"].max())
        sub = s360[s360["year"] == ly]
        n_peer = int((sub["rater_type"] == "peer").sum())
        n_dr = int((sub["rater_type"] == "direct_report").sum())
        lines_meta.append(
            f"다면진단 최신 연도({ly}, 필터 내): 동료 **{n_peer}건**, 산하 **{n_dr}건**."
        )

    if not pers.empty:
        by_trait = pers.groupby("trait_label")["year"].nunique()
        sticky = by_trait[by_trait >= 2].sort_values(ascending=False)
        if len(sticky):
            tops = " · ".join(sticky.head(4).index.astype(str).tolist())
            lines_meta.append(f"여러 해에 반복된 성격 태그: {tops}.")

    if not sess.empty:
        sess2 = sess.sort_values("year")
        last = sess2.iloc[-1]
        sn = last["session_name"]
        if pd.isna(sn):
            sn = "세션"
        lines_meta.append(
            f"최근 세션: **{_safe_int(last['year'])}** · {sn} (원문은 세션 탭)."
        )

    caption = (
        "가중 규칙: **2차 평가·2차 세션** > 1차, **필터 내 최신 연도**에 가중, "
        "다면은 **보완점**과 **산하** 응답에 높은 가중, 성격은 **trait_order 상위(1에 가까울수록)** 가중."
    )

    sections: list[dict] = []
    if lines_perf:
        sections.append({"title": "① 성과 개요", "lines": lines_perf})
    if kw_lines:
        sections.append({"title": "② 키워드 종합 (경중·출처·최신성 반영)", "lines": kw_lines})
    if lines_meta:
        sections.append({"title": "③ 데이터 커버리지", "lines": lines_meta})
    if not sections:
        sections = [{"title": "요약", "lines": ["표시할 요약이 없습니다. 데이터·연도 필터를 확인하세요."]}]

    return {"caption": caption, "sections": sections}


# ---------------------------------------------------------------------------
# Streamlit
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="직책자 프로파일링",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("직책자 프로파일링 대시보드")
st.caption(
    "다면진단(서술) · 성과평가 · 성격평가 · HR 세션을 연도 맥락으로 묶어 봅니다. "
    "요약 문구는 **참고용**이며, 판단의 근거는 내부 규정과 **원문 기록**을 따릅니다."
)

with st.expander("기획·데이터 매핑 (요약)", expanded=False):
    st.markdown(
        """
        | 구분 | 내용 | 화면 |
        |------|------|------|
        | 다면진단 | 동료·산하 최대 10명급 서술(강점/보완), 연 1회 | 유형·연도별 Expander |
        | 성과평가 | S~D 등급, 1차/2차 종합 의견 | 추이 차트 + 연도별 의견 |
        | 성격평가 | 상위직이 연 최대 5개 태그 | 연도 뱃지 + 태그 누적 빈도 |
        | 세션정보 | HR 면담 등, 1차/2차 서술 | 연도·회차 목록 |
        """
    )


@st.cache_data
def _bundle():
    return {
        "master": load_master(),
        "perf": load_performance(),
        "n360": load_360_narrative(),
        "pers": load_personality(),
        "sess": load_sessions(),
    }


b = _bundle()
master = b["master"]
df_perf = b["perf"]
df_360 = b["n360"]
df_pers = b["pers"]
df_sess = b["sess"]

if master.empty:
    st.error("`data/sample_executive_master.csv`가 없습니다. `data/` 폴더를 확인하세요.")
    st.stop()

labels = master.apply(lambda r: f"{r['display_label']} [{r['employee_ref']}]", axis=1).tolist()
ref_map = {f"{r['display_label']} [{r['employee_ref']}]": r["employee_ref"] for _, r in master.iterrows()}

with st.sidebar:
    st.header("대상 · 필터")
    choice = st.selectbox("직책자", options=labels, index=0)
    ref = ref_map[choice]
    row = master[master["employee_ref"] == ref].iloc[0]
    st.markdown(f"**직책** {row.get('role_title', '—')}")

    years_perf = sorted(slice_emp(df_perf, ref)["year"].unique().tolist()) if not slice_emp(df_perf, ref).empty else []
    years_all = sorted(
        set(years_perf)
        | set(slice_emp(df_360, ref)["year"].unique().tolist())
        | set(slice_emp(df_pers, ref)["year"].unique().tolist())
        | set(slice_emp(df_sess, ref)["year"].unique().tolist())
    )
    if years_all:
        y_min, y_max = int(min(years_all)), int(max(years_all))
        if y_min == y_max:
            yr_lo = yr_hi = y_min
            st.caption(f"연도 범위: **{y_min}** (단일 연도만 존재)")
        else:
            yr_lo, yr_hi = st.slider("연도 범위 (요약·일부 표)", y_min, y_max, (y_min, y_max))
    else:
        yr_lo, yr_hi = 2000, 2030

    st.caption("데모용 샘플 CSV입니다. 실제 연동 시 스키마·권한을 맞추세요.")

perf_e = slice_emp(df_perf, ref)
perf_e = perf_e[(perf_e["year"] >= yr_lo) & (perf_e["year"] <= yr_hi)] if not perf_e.empty else perf_e
n360_e = slice_emp(df_360, ref)
pers_e = slice_emp(df_pers, ref)
sess_e = slice_emp(df_sess, ref)
pers_e_win = (
    pers_e[(pers_e["year"] >= yr_lo) & (pers_e["year"] <= yr_hi)]
    if not pers_e.empty and "year" in pers_e.columns
    else pers_e
)
perf_win = _filter_year(slice_emp(df_perf, ref), yr_lo, yr_hi)

tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["한눈에 요약", "성과평가", "다면진단", "성격평가", "세션정보", "데이터 정의"]
)

with tab0:
    st.subheader("요약 (출처·서열·최신성 가중)")
    summ = build_prioritized_summary(ref, df_perf, df_360, df_pers, df_sess, yr_lo, yr_hi)
    st.caption(summ["caption"])
    for sec in summ["sections"]:
        st.markdown(f"##### {sec['title']}")
        for line in sec["lines"]:
            st.markdown(f"- {line}")
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(fig_grade_timeline(perf_win), use_container_width=True)
    with c2:
        st.plotly_chart(fig_trait_frequency(pers_e_win), use_container_width=True)

with tab1:
    st.subheader("성과평가 — 등급 및 1차·2차 종합 의견")
    if perf_e.empty:
        st.info("해당 기간 성과평가 데이터가 없습니다.")
    else:
        st.plotly_chart(fig_grade_timeline(perf_win), use_container_width=True)
        st.dataframe(
            perf_e.sort_values("year", ascending=False)[["year", "grade", "opinion_primary", "opinion_secondary"]],
            use_container_width=True,
            height=min(400, 60 + len(perf_e) * 38),
        )
        for _, r in perf_e.sort_values("year", ascending=False).iterrows():
            with st.expander(f"{int(r['year'])}년 — 등급 **{r['grade']}**"):
                st.markdown("**1차 평가자 종합 의견**")
                st.write(r["opinion_primary"])
                st.markdown("**2차 평가자 종합 의견**")
                st.write(r["opinion_secondary"])

with tab2:
    st.subheader("다면진단 — 동료·산하 서술형 (강점 / 보완점)")
    n360_f = n360_e[(n360_e["year"] >= yr_lo) & (n360_e["year"] <= yr_hi)] if not n360_e.empty else n360_e
    if n360_f.empty:
        st.info("다면진단 서술 데이터가 없습니다.")
    else:
        year_pick = st.selectbox(
            "연도 선택",
            options=sorted(n360_f["year"].unique().tolist(), reverse=True),
            key="n360_year",
        )
        sub = n360_f[n360_f["year"] == year_pick]
        p1, p2 = st.columns(2)
        p1.metric("동료 응답 수", int((sub["rater_type"] == "peer").sum()))
        p2.metric("산하 응답 수", int((sub["rater_type"] == "direct_report").sum()))
        st.caption("실제 운영 시 응답자는 비식별 처리하고, 산하 최대 10명 등 정책을 반영하세요.")

        for rtype in ["peer", "direct_report"]:
            part = sub[sub["rater_type"] == rtype].sort_values("rater_seq")
            label = RATER_LABELS.get(rtype, rtype)
            st.markdown(f"#### {label}")
            if part.empty:
                st.caption("해당 유형 응답 없음")
                continue
            for _, row in part.iterrows():
                idx = int(row["rater_seq"])
                with st.expander(f"{label} 응답 #{idx}"):
                    st.markdown("**강점**")
                    st.write(row["strength_text"])
                    st.markdown("**보완점**")
                    st.write(row["improvement_text"])

with tab3:
    st.subheader("성격평가 — 연도별 태그(최대 5) · 누적 빈도")
    if pers_e.empty:
        st.info("성격평가 데이터가 없습니다.")
    else:
        st.plotly_chart(fig_trait_frequency(pers_e), use_container_width=True)
        for y in sorted(pers_e["year"].unique(), reverse=True):
            chunk = pers_e[pers_e["year"] == y].sort_values("trait_order")
            st.markdown(f"**{int(y)}년**")
            cols = st.columns(5)
            labels_row = chunk["trait_label"].tolist()
            for i, lab in enumerate(labels_row[:5]):
                cols[i % 5].markdown(f"`{lab}`")

with tab4:
    st.subheader("세션정보 — HR·직책자 면담 (1차·2차 서술)")
    if sess_e.empty:
        st.info("세션 데이터가 없습니다.")
    else:
        for _, r in sess_e.sort_values("year", ascending=False).iterrows():
            with st.expander(f"{int(r['year'])}년 · {r['session_name']}"):
                st.markdown("**1차 기록**")
                st.write(r["opinion_primary"])
                st.markdown("**2차 기록**")
                st.write(r["opinion_secondary"])

with tab5:
    st.markdown(
        """
        **파일 위치**: 프로젝트 `data/` (UTF-8 BOM)

        | 파일 | 설명 |
        |------|------|
        | `sample_executive_master.csv` | `employee_ref`, `display_label`, `role_title` |
        | `sample_executive_performance.csv` | `year`, `grade`, `opinion_primary`, `opinion_secondary` |
        | `sample_executive_360_narrative.csv` | `year`, `rater_type`(peer/direct_report), `rater_seq`, `strength_text`, `improvement_text` |
        | `sample_executive_personality.csv` | `year`, `trait_order`(1~5), `trait_label` |
        | `sample_executive_sessions.csv` | `year`, `session_name`, `opinion_primary`, `opinion_secondary` |

        실제 연동 시 컬럼명을 HR 시스템에 맞게 매핑하고, 개인정보·열람 로그를 적용하세요.
        """
    )
