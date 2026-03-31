"""
적임자 선발 참고 대시보드 (Streamlit)
기획: docs/hr-candidate-fit-dashboard-plan.md

실행: streamlit run hr_candidate_dashboard.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from hr_charts import fig_compliance_bars, fig_fit_score_bars, fig_radar_compare
from hr_data import (
    add_track_evaluation,
    aggregate_requirement_pass_rates,
    evaluate_row_for_track,
    filter_candidates,
    load_candidates,
    load_tracks,
    track_by_id,
)

st.set_page_config(
    page_title="적임자 선발 참고 대시보드",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "hr_audit_log" not in st.session_state:
    st.session_state.hr_audit_log = []


@st.cache_data
def _cached_tracks(path_str: str) -> dict:
    return load_tracks(Path(path_str) if path_str else None)


@st.cache_data
def _cached_candidates(path_str: str) -> pd.DataFrame:
    return load_candidates(Path(path_str) if path_str else None)


tracks_path = str(Path(__file__).resolve().parent / "config" / "tracks.json")
candidates_path = str(Path(__file__).resolve().parent / "data" / "sample_hr_candidates.csv")

tracks_cfg = _cached_tracks(tracks_path)
candidates_raw = _cached_candidates(candidates_path)

st.title("📋 적임자 선발 · 참고용 대시보드")
st.error(
    "**자동 선발이 아닙니다.** 최종 판단은 내부 규정·면담·검증 절차에 따릅니다. "
    "점수·표시는 규칙 기반 참고 지표이며 법적 효력이 없습니다."
)
st.caption(
    f"데이터 기준일: **{tracks_cfg.get('data_reference_date', '—')}** · "
    f"{tracks_cfg.get('data_source_note', '')}"
)

track_options = {t["id"]: t["name"] for t in tracks_cfg.get("tracks", [])}

with st.sidebar:
    st.header("선발 트랙 · 필터")
    track_id = st.selectbox(
        "선발 분야(트랙)",
        options=list(track_options.keys()),
        format_func=lambda x: track_options[x],
    )
    track = track_by_id(tracks_cfg, track_id)

    st.subheader("요건 엄격도")
    strict_only = st.checkbox("필수 충족 후보만 목록에 표시", value=False)
    pref_weight = st.slider("우대 가중 배율 (점수에 곱함)", 0.5, 1.5, 1.0, 0.1)

    st.subheader("후보 필터")
    dept_opts = ["(전체)"] + sorted(candidates_raw["dept"].dropna().unique().tolist())
    jf_opts = ["(전체)"] + sorted(candidates_raw["job_family"].dropna().unique().tolist())
    dept = st.selectbox("부서", dept_opts)
    job_family = st.selectbox("직무군", jf_opts)
    tmin, tmax = int(candidates_raw["tenure_months"].min()), int(candidates_raw["tenure_months"].max())
    tenure_range = st.slider("근속(월)", tmin, tmax, (tmin, tmax))
    english_extra = st.number_input("추가 최소 TOEIC (필터)", 0, 990, 0, 10)
    abroad_min = st.number_input("최소 해외 누적(월)", 0, 120, 0, 1)
    family_only = st.checkbox("가족 동반 가능(Y)만", value=False)

st.subheader(f"트랙 요건: {track['name']}")
st.markdown(track.get("summary", ""))
req_cols = st.columns(2)
req_items = track.get("requirements") or []
for i, req in enumerate(req_items):
    kind = req.get("kind")
    label = req.get("label", "")
    if kind == "required":
        req_cols[i % 2].markdown(f":red[**[필수]**] {label}")
    elif kind == "exclude":
        req_cols[i % 2].markdown(f":orange[**[제외]**] {label}")
    else:
        req_cols[i % 2].markdown(label)
pref_items = track.get("preferred") or []
if pref_items:
    st.markdown("**우대(가점 규칙)**")
    for p in pref_items:
        st.markdown(f"- :blue[{p.get('label', '')}] (가중 {p.get('weight', 0)})")

filtered = filter_candidates(
    candidates_raw,
    dept=None if dept == "(전체)" else dept,
    job_family=None if job_family == "(전체)" else job_family,
    tenure_min=tenure_range[0],
    tenure_max=tenure_range[1],
    english_min_extra=english_extra,
    months_abroad_min=abroad_min,
    family_relocate_only=family_only,
)

full_ev = (
    add_track_evaluation(filtered, track, weight_multiplier=pref_weight)
    if len(filtered)
    else pd.DataFrame()
)
n_all = len(full_ev)
n_ok = int(full_ev["meets_required"].sum()) if n_all else 0
eval_df = full_ev[full_ev["meets_required"]].copy() if strict_only else full_ev.copy()

k1, k2, k3, k4 = st.columns(4)
k1.metric("필터 후 인원", len(eval_df))
k2.metric("필수 충족(필터 전체 기준)", f"{n_ok} / {n_all}")
if len(eval_df):
    med_toeic = float(eval_df["english_toeic"].median())
else:
    med_toeic = float("nan")
k3.metric("표시 중 TOEIC 중앙값", "—" if pd.isna(med_toeic) else f"{med_toeic:.0f}")
k4.metric("우대 배율", f"{pref_weight:.1f}x")

tab_list, tab_cmp, tab_sum = st.tabs(["후보 목록", "비교 뷰", "요건 충족 요약"])

display_cols = [
    "employee_ref",
    "dept",
    "job_family",
    "tenure_months",
    "english_toeic",
    "months_abroad_total",
    "family_can_relocate",
    "travel_readiness_1_5",
    "disciplinary_issue",
    "return_obligation_ok",
    "meets_required",
    "fit_score_0_100",
]

with tab_list:
    q = st.text_input("검색 (사번·부서·직무군 부분 일치)", "")
    show = eval_df.copy()
    if q.strip():
        m = show["employee_ref"].astype(str).str.contains(q, case=False)
        m |= show["dept"].astype(str).str.contains(q, case=False)
        m |= show["job_family"].astype(str).str.contains(q, case=False)
        show = show.loc[m]
    disp = show[[c for c in display_cols if c in show.columns]].copy()
    disp.insert(0, "필수충족", show["meets_required"].map({True: "O", False: "X"}))
    st.dataframe(disp, use_container_width=True, hide_index=True)

    csv_bytes = disp.to_csv(index=False).encode("utf-8-sig")
    if st.download_button(
        "표시 중 목록 CSV 내려받기",
        data=csv_bytes,
        file_name="hr_candidate_shortlist.csv",
        mime="text/csv",
    ):
        st.session_state.hr_audit_log.append(
            {
                "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                "action": "csv_download",
                "track": track_id,
                "rows": len(disp),
            }
        )

with tab_cmp:
    opts = eval_df["employee_ref"].astype(str).tolist()
    picked = st.multiselect("비교할 후보 (최대 5명)", options=opts, max_selections=5)
    if picked:
        sub = eval_df[eval_df["employee_ref"].astype(str).isin(picked)]
        st.plotly_chart(fig_radar_compare(sub), use_container_width=True)
        st.plotly_chart(fig_fit_score_bars(sub), use_container_width=True)
        with st.expander("선택 인원 상세(우대 항목)"):
            for _, row in sub.iterrows():
                ev = evaluate_row_for_track(row, track)
                st.markdown(f"**{row['employee_ref']}**")
                for d in ev.get("preferred_detail") or []:
                    mark = "✓" if d.get("met") else "·"
                    st.markdown(f"- {mark} {d.get('label')}")
    else:
        st.info("목록 탭에서 필터한 뒤, 여기서 후보를 선택하세요.")

with tab_sum:
    summ = aggregate_requirement_pass_rates(filtered, track)
    st.plotly_chart(fig_compliance_bars(summ), use_container_width=True)
    st.dataframe(summ, use_container_width=True, hide_index=True)
    st.plotly_chart(fig_fit_score_bars(eval_df), use_container_width=True)

with st.expander("데이터 정의 · 개인정보 · 감사"):
    st.markdown(
        """
        - **employee_ref**: 데모용 비식별 코드. 실제 운영 시 사번·이름 처리 정책을 따르세요.
        - **자가신고**: `family_can_relocate`, `travel_readiness_1_5` 등은 예시 필드입니다.
        - **징계·건강**: 민감정보는 목적·권한에 맞게 별도 관리하세요.
        - **차별 금지**: 성별·연령 등 보호 속성은 본 샘플에 포함하지 않았으며, 점수에도 넣지 마세요.
        """
    )
    if st.session_state.hr_audit_log:
        st.markdown("**이 세션 CSV 다운로드 기록**")
        st.json(st.session_state.hr_audit_log[-10:])
