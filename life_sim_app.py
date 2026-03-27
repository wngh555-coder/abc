"""
선택 기반 인생 시뮬레이터 + 데이터 대시보드 (Streamlit)
기획: docs/choice-based-life-simulator-dashboard-plan.md

실행: streamlit run life_sim_app.py
"""

from __future__ import annotations

import html as html_mod
from pathlib import Path

import pandas as pd
import streamlit as st

from life_sim_charts import (
    fig_current_bars,
    fig_radar,
    fig_sparkline_grid,
    fig_stat_lines,
    fig_timeline_heatmap,
    fig_turn_deltas,
)
from life_sim_state import (
    STAT_LABELS_KO,
    apply_choice,
    format_life_review,
    format_newspaper_epilogue,
    format_turn_state_summary,
    get_node,
    load_scenario,
    new_game,
    state_from_json,
    state_to_json,
    timeline_to_csv_bytes,
)

st.set_page_config(
    page_title="선택으로 보는 인생 시뮬",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

SESSION_STATE = "life_sim_state"
SESSION_SCENARIO = "life_sim_scenario"
SESSION_NAME = "life_sim_protagonist_name"

# 스탯 카드: (이모지, 힌트, 그라데이션 시작, 테두리/포인트 색)
_STAT_CARD_THEME: dict[str, tuple[str, str, str, str]] = {
    "health": ("🩺", "몸 상태", "#ecfdf5", "#34d399"),
    "wealth": ("💰", "통장·살림", "#eff6ff", "#60a5fa"),
    "happiness": ("🌤", "기분·만족", "#fffbeb", "#fbbf24"),
    "career": ("💼", "일·앞길", "#f5f3ff", "#a78bfa"),
    "relationship": ("🤝", "사람·믿음", "#fdf2f8", "#f472b6"),
}


def _protagonist_name() -> str:
    return str(st.session_state.get(SESSION_NAME) or "김민준").strip() or "김민준"


def _inject_theme_css() -> None:
    st.markdown(
        """
<style>
  [data-testid="stAppViewContainer"] {
    background: linear-gradient(165deg, #ecfdf5 0%, #e0f2fe 38%, #ede9fe 72%, #fdf4ff 100%) !important;
  }
  [data-testid="stHeader"] { background: rgba(255,255,255,0.25) !important; backdrop-filter: blur(10px); }
  .ls-hero {
    background: linear-gradient(120deg, rgba(13,148,136,0.92), rgba(59,130,246,0.88));
    color: #f8fafc !important;
    padding: 1.1rem 1.35rem 1.1rem 1.35rem;
    border-radius: 16px;
    box-shadow: 0 8px 28px rgba(13,148,136,0.28);
    margin-bottom: 0.75rem;
    border: 1px solid rgba(255,255,255,0.25);
  }
  .ls-hero h1 { color: #f8fafc !important; font-size: 1.65rem !important; margin: 0 0 0.35rem 0 !important; }
  .ls-hero .caption { color: rgba(248,250,252,0.92) !important; font-size: 0.95rem !important; }
  .ls-bar {
    height: 10px;
    background: rgba(255,255,255,0.32);
    border-radius: 99px;
    margin-top: 0.75rem;
    overflow: hidden;
  }
  .ls-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #fde68a, #fbbf24);
    border-radius: 99px;
  }
  .ls-bar-label { font-size: 0.82rem; margin-top: 0.45rem; color: rgba(248,250,252,0.95); }
  .ls-stat-card {
    border-radius: 14px;
    padding: 0.65rem 0.5rem 0.55rem 0.5rem;
    text-align: center;
    border: 1px solid rgba(15,23,42,0.08);
    box-shadow: 0 4px 14px rgba(15,23,42,0.06);
    min-height: 5.5rem;
  }
  .ls-stat-card .ls-lab { font-size: 0.82rem; font-weight: 600; opacity: 0.92; margin-bottom: 0.15rem; }
  .ls-stat-card .ls-val { font-size: 1.75rem; font-weight: 800; color: #0f172a; line-height: 1.15; }
  .ls-stat-card .ls-delta { font-size: 0.78rem; margin-top: 0.2rem; font-weight: 600; }
  [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.65) !important;
    border-radius: 12px !important;
    padding: 4px !important;
    gap: 4px !important;
    border: 1px solid rgba(13,148,136,0.12) !important;
  }
  button[data-baseweb="tab"] {
    border-radius: 10px !important;
  }
  button[data-baseweb="tab"][aria-selected="true"] {
    background: linear-gradient(135deg, rgba(13,148,136,0.2), rgba(59,130,246,0.18)) !important;
    color: #0f766e !important;
    font-weight: 600 !important;
  }
</style>
        """,
        unsafe_allow_html=True,
    )


def _stat_cards_row(
    keys: tuple[str, ...],
    stats: dict,
    prev_stats: dict[str, float] | None,
    turn: int,
) -> None:
    cols = st.columns(len(keys), gap="small")
    for i, k in enumerate(keys):
        if i >= len(cols):
            break
        v = float(stats.get(k, 0))
        emoji, _hint, bg, border = _STAT_CARD_THEME.get(
            k, ("📊", "", "#f8fafc", "#94a3b8")
        )
        lab = STAT_LABELS_KO.get(k, k)
        if prev_stats is not None and k in prev_stats:
            d = v - float(prev_stats.get(k, v))
            if d > 0:
                delta_html = f'<span class="ls-delta" style="color:#059669;">▲ {d:+.0f}</span>'
            elif d < 0:
                delta_html = f'<span class="ls-delta" style="color:#dc2626;">▼ {d:+.0f}</span>'
            else:
                delta_html = '<span class="ls-delta" style="color:#64748b;">±0</span>'
        elif turn > 0:
            delta_html = '<span class="ls-delta" style="color:#94a3b8;">—</span>'
        else:
            delta_html = '<span class="ls-delta" style="color:#94a3b8;">시작</span>'

        card = (
            f'<div class="ls-stat-card" style="background:linear-gradient(160deg,{html_mod.escape(bg)},#ffffff);'
            f'border-color:{html_mod.escape(border)}55;">'
            f'<div class="ls-lab" style="color:#0f172a;">{html_mod.escape(emoji)} {html_mod.escape(lab)}</div>'
            f'<div class="ls-val">{html_mod.escape(f"{v:.0f}")}</div>'
            f"{delta_html}</div>"
        )
        with cols[i]:
            st.markdown(card, unsafe_allow_html=True)


with st.sidebar:
    st.header("게임")
    scenario_path_input = st.text_input(
        "시나리오 파일 경로 (비우면 기본값)",
        value="",
        help="프로젝트 폴더 기준으로 적어 주세요. 바꾼 뒤 아래 버튼으로 불러옵니다.",
    )
    path_norm = scenario_path_input.strip() or None

    if st.button("이 경로로 불러오기 (진행은 처음부터)", use_container_width=True):
        sc = load_scenario(Path(path_norm) if path_norm else None)
        st.session_state[SESSION_SCENARIO] = sc
        st.session_state[SESSION_STATE] = new_game(sc)
        st.rerun()

    if SESSION_SCENARIO not in st.session_state or SESSION_STATE not in st.session_state:
        sc = load_scenario(Path(path_norm) if path_norm else None)
        st.session_state[SESSION_SCENARIO] = sc
        st.session_state[SESSION_STATE] = new_game(sc)

    if SESSION_NAME not in st.session_state:
        st.session_state[SESSION_NAME] = "김민준"

    scenario = st.session_state[SESSION_SCENARIO]
    state = st.session_state[SESSION_STATE]

    if st.button("새 게임", use_container_width=True):
        st.session_state[SESSION_STATE] = new_game(scenario)
        st.rerun()

    st.divider()
    st.subheader("저장 / 불러오기")
    st.download_button(
        "진행 상황 저장 (JSON)",
        data=state_to_json(state).encode("utf-8"),
        file_name="life_sim_save.json",
        mime="application/json",
        use_container_width=True,
    )
    st.download_button(
        "기록 표로 저장 (CSV)",
        data=timeline_to_csv_bytes(state, scenario),
        file_name="life_sim_timeline.csv",
        mime="text/csv",
        use_container_width=True,
    )
    up = st.file_uploader("저장해 둔 JSON 불러오기", type=["json"])
    if up is not None and st.button("불러온 JSON 적용", use_container_width=True):
        try:
            raw = up.read().decode("utf-8")
            loaded = state_from_json(raw)
            if loaded.get("scenario_id") != scenario.get("scenario_id"):
                st.error("지금 쓰는 시나리오와 맞지 않아요. 같은 시나리오로 저장한 파일을 써 주세요.")
            else:
                st.session_state[SESSION_STATE] = loaded
                st.success("불러왔어요.")
                st.rerun()
        except Exception as e:
            st.error(f"불러오기에 실패했어요: {e}")

    st.divider()
    st.subheader("주인공 이름")
    st.caption("이름은 끝날 때 나오는 글·요약에 씁니다.")
    st.text_input("이름", key=SESSION_NAME)

    with st.expander("📖 지금 상태 한 줄 요약", expanded=False):
        st.markdown(
            format_turn_state_summary(state, scenario, _protagonist_name())
        )

state = st.session_state[SESSION_STATE]
scenario = st.session_state[SESSION_SCENARIO]
protagonist_name = _protagonist_name()
node = get_node(scenario, state["node_id"])
max_turns = int(scenario["max_turns"])
turn = int(state["turn"])
prog = min(1.0, turn / max_turns) if max_turns else 0.0
keys = tuple(scenario.get("stat_keys") or ())
stats = state["stats"]
timeline = state.get("timeline") or []
prev_stats = (timeline[-2].get("stats_after") or {}) if len(timeline) >= 2 else None

_inject_theme_css()

_pct = int(round(min(1.0, max(0.0, prog)) * 100))
st.markdown(
    f"""
<div class="ls-hero">
  <h1>🌿 선택으로 보는 인생 시뮬</h1>
  <div class="caption">이번 이야기: <strong>{html_mod.escape(str(scenario.get("title", "")))}</strong>
  · 점수는 0~100 · 배우기·실험용</div>
  <div class="ls-bar"><div class="ls-bar-fill" style="width:{_pct}%"></div></div>
  <div class="ls-bar-label">선택 {html_mod.escape(str(turn))}번 / 최대 {html_mod.escape(str(max_turns))}번
  · 나이 {html_mod.escape(str(state["age"]))}세</div>
</div>
    """,
    unsafe_allow_html=True,
)

_stat_cards_row(keys, stats, prev_stats, turn)

game_col, dash_col = st.columns([1, 1.2], gap="large")

with game_col:
    st.subheader(node.get("title") or state["node_id"])
    if not state["meta"]["ended"]:
        st.caption(f"지금은 **{state['age']}살** 무렵이에요. 아래에서 하나만 고르세요.")
    st.markdown(node.get("body") or "")

    if state["meta"]["ended"]:
        st.markdown(
            format_newspaper_epilogue(state, scenario, protagonist_name),
            unsafe_allow_html=True,
        )
        with st.expander("짧은 요약 (점수 기준)"):
            st.markdown(format_life_review(state, scenario))
        st.success("이번 판이 끝났어요. 오른쪽에서 그래프로 흐름을 볼 수 있어요.")
        if st.button("같은 이야기로 다시 하기", key="replay"):
            st.session_state[SESSION_STATE] = new_game(scenario)
            st.rerun()
    else:
        st.markdown("**어떻게 할까요?**")
        for ch in node.get("choices") or []:
            cid = ch.get("id")
            label = ch.get("label") or cid
            if st.button(label, key=f"choice_{cid}", use_container_width=True):
                new_state, err = apply_choice(state, scenario, str(cid))
                if err:
                    st.warning(err)
                else:
                    st.session_state[SESSION_STATE] = new_state
                    st.rerun()

with dash_col:
    st.subheader("그래프로 보기")
    tab_a, tab_b, tab_c, tab_d = st.tabs(
        ["한눈에", "나이 따라 변화", "턴·막대", "표로 보기"]
    )

    with tab_a:
        a1, a2 = st.columns(2, gap="medium")
        with a1:
            st.plotly_chart(fig_current_bars(stats, scenario), use_container_width=True)
        with a2:
            st.plotly_chart(fig_radar(stats, scenario), use_container_width=True)

    with tab_b:
        st.plotly_chart(fig_stat_lines(state, scenario), use_container_width=True)
        st.plotly_chart(fig_sparkline_grid(state, scenario), use_container_width=True)

    with tab_c:
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            st.plotly_chart(fig_turn_deltas(state, scenario), use_container_width=True)
        with c2:
            st.plotly_chart(fig_timeline_heatmap(state, scenario), use_container_width=True)

    with tab_d:
        rows = []
        for e in timeline:
            sa = e.get("stats_after") or {}
            row = {
                "몇 번째": e["turn"],
                "장면": e.get("node_id"),
                "고른 것": e.get("choice_label") or "—",
                "시각": e.get("ts"),
            }
            for k in keys:
                row[STAT_LABELS_KO.get(k, k)] = sa.get(k)
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with st.expander("안내 (읽어 주세요)"):
    st.markdown(
        """
        - 이 앱은 **선택과 점수가 어떻게 엮이는지** 보는 **실험용**이에요. 투자·병원·법률 같은 **조언이 아니에요.**
        - 이야기와 숫자는 **가짜**예요. 진짜 인생만큼 복잡하지 않습니다.
        - 긴 설명은 사이드바 **「지금 상태 한 줄 요약」**에서 볼 수 있어요. **진단이 아니에요.**
        - 창을 닫으면 진행이 사라질 수 있어요. **JSON으로 저장**해 두는 걸 추천해요.
        """
    )
