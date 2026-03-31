from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.charts import match_score_heatmap, radar_tactical_indices, tournament_path_bar
from src.simulator import simulate_match_distribution
from src.tactics import PRESETS, Tactics, TeamIndices, tactics_to_indices
from src.tournament import simulate_group_monte_carlo, simulate_tournament_path_monte_carlo

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


@st.cache_data(show_spinner=False)
def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load_teams() -> dict:
    return load_json(DATA_DIR / "teams.json")


@st.cache_data(show_spinner=False)
def load_tournament() -> dict:
    return load_json(DATA_DIR / "tournament_2026.json")


def _make_team_strength(teams: dict, code: str):
    from src.simulator import TeamStrength

    t = teams[code]
    return TeamStrength(
        code=code,
        name=t["name"],
        attack=float(t["attack"]),
        defense=float(t["defense"]),
        midfield=float(t["midfield"]),
        transition=float(t["transition"]),
        stamina=float(t["stamina"]),
    )


def _expected_points_from_wdl(win: float, draw: float, loss: float) -> float:
    return 3.0 * win + 1.0 * draw + 0.0 * loss


def _format_prob(p: float) -> str:
    return f"{p * 100:.1f}%"


def _scenario_summary(t: Tactics, indices: TeamIndices, group_qualify_prob: float, r16_prob: float) -> str:
    press = t.pressing
    line = t.line_height
    poss = t.possession
    direct = t.directness
    risk = t.risk_profile
    vol = indices.volatility

    statements: list[str] = []

    if vol >= 62:
        statements.append("현재 설정은 `리스크(변동성)`가 큰 편이라 결과가 흔들릴 가능성이 큽니다.")
    elif vol <= 40:
        statements.append("현재 설정은 `리스크(변동성)`가 낮아 점수 격차가 비교적 안정적으로 수렴하는 경향입니다.")
    else:
        statements.append("현재 설정은 `리스크(변동성)`가 중간 수준으로 공격과 안정의 균형이 잡힌 편입니다.")

    if press >= 70 and line >= 65:
        statements.append("`압박`과 `수비 라인 높이`를 함께 높이면 상대를 밀어붙이지만 뒷공간 리스크가 동반됩니다.")
    elif press >= 70 and line < 45:
        statements.append("`압박`을 높였지만 라인을 낮추면 공수 균형은 좋아지되 공격 전환의 스파이크가 줄 수 있습니다.")
    elif press < 40 and line >= 65:
        statements.append("`압박`은 낮고 라인은 높으면 점유를 빼앗길 때 전환 실점 가능성이 커질 수 있습니다.")
    else:
        statements.append("현재 압박/라인 조합은 데모 모델 기준으로 공수 충돌이 비교적 완만한 편입니다.")

    if poss >= 65 and direct >= 65:
        statements.append("`점유`와 `직선성`을 같이 높이면 주도권을 유지하면서도 빠른 찬스를 만들 가능성이 있습니다.")
    elif poss >= 65:
        statements.append("`점유 지향`이 높아 안정성(수비/미드필드)이 커지지만 전환 속도는 둔해질 수 있습니다.")
    elif direct >= 65:
        statements.append("`공격 직선성`이 높아 역습/전환 찬스가 늘지만 득점이 들쑥날쑥해질 수 있습니다.")

    if risk == "보수":
        statements.append("`보수`는 기대 득점보다 안정(실점 억제)을 우선시하는 방향으로 인덱스를 조정합니다.")
    elif risk == "공격":
        statements.append("`공격`은 기대 득점 상단을 키우는 대신 변동성을 동반하는 방향입니다.")
    else:
        statements.append("`균형`은 공격/수비 트레이드오프를 완만하게 반영합니다.")

    statements.append(f"조 통과 확률(상위 2): {_format_prob(group_qualify_prob)}")
    statements.append(f"16강 진출 확률: {_format_prob(r16_prob)}")

    return " ".join(statements)


def main() -> None:
    st.set_page_config(
        page_title="대한민국 2026 월드컵 전술 시뮬레이터",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    teams = load_teams()
    tournament = load_tournament()

    st.sidebar.header("전술 입력")

    preset_names = list(PRESETS.keys())
    preset = st.sidebar.selectbox("프리셋", preset_names, index=0)
    default_t = PRESETS[preset]

    if "tactics_state" not in st.session_state:
        st.session_state["tactics_state"] = {
            "formation": default_t.formation,
            "pressing": default_t.pressing,
            "line_height": default_t.line_height,
            "possession": default_t.possession,
            "directness": default_t.directness,
            "wing_focus": default_t.wing_focus,
            "set_piece_focus": default_t.set_piece_focus,
            "rotation": default_t.rotation,
            "ace_dependency": default_t.ace_dependency,
            "risk_profile": default_t.risk_profile,
        }

    def apply_preset() -> None:
        t = PRESETS[preset]
        st.session_state["tactics_state"].update(
            {
                "formation": t.formation,
                "pressing": t.pressing,
                "line_height": t.line_height,
                "possession": t.possession,
                "directness": t.directness,
                "wing_focus": t.wing_focus,
                "set_piece_focus": t.set_piece_focus,
                "rotation": t.rotation,
                "ace_dependency": t.ace_dependency,
                "risk_profile": t.risk_profile,
            }
        )
        st.rerun()

    if st.sidebar.button("프리셋 적용"):
        apply_preset()

    ts = st.session_state["tactics_state"]

    st.sidebar.divider()

    formation = st.sidebar.selectbox(
        "포메이션",
        ["4-2-3-1", "4-3-3", "3-4-3", "4-4-2"],
        index=["4-2-3-1", "4-3-3", "3-4-3", "4-4-2"].index(ts["formation"]),
    )
    pressing = st.sidebar.slider("압박 강도", 0, 100, int(ts["pressing"]))
    line_height = st.sidebar.slider("수비 라인 높이", 0, 100, int(ts["line_height"]))
    possession = st.sidebar.slider("점유율 지향도", 0, 100, int(ts["possession"]))
    directness = st.sidebar.slider("공격 직선성", 0, 100, int(ts["directness"]))
    wing_focus = st.sidebar.slider("측면 활용 비중", 0, 100, int(ts["wing_focus"]))
    set_piece_focus = st.sidebar.slider("세트피스 집중도", 0, 100, int(ts["set_piece_focus"]))
    rotation = st.sidebar.slider("로테이션 강도", 0, 100, int(ts["rotation"]))
    ace_dependency = st.sidebar.slider("에이스 의존도", 0, 100, int(ts["ace_dependency"]))
    risk_profile = st.sidebar.selectbox(
        "리스크 성향",
        ["보수", "균형", "공격"],
        index=["보수", "균형", "공격"].index(ts["risk_profile"]),
    )

    ts.update(
        {
            "formation": formation,
            "pressing": pressing,
            "line_height": line_height,
            "possession": possession,
            "directness": directness,
            "wing_focus": wing_focus,
            "set_piece_focus": set_piece_focus,
            "rotation": rotation,
            "ace_dependency": ace_dependency,
            "risk_profile": risk_profile,
        }
    )

    korea_code = "KOR"
    group_codes = ["KOR", "MEX", "SUI", "SEN"]

    tactics = Tactics(
        formation=formation,  # type: ignore[arg-type]
        pressing=int(pressing),
        line_height=int(line_height),
        possession=int(possession),
        directness=int(directness),
        wing_focus=int(wing_focus),
        set_piece_focus=int(set_piece_focus),
        rotation=int(rotation),
        ace_dependency=int(ace_dependency),
        risk_profile=risk_profile,  # type: ignore[arg-type]
    )

    indices = tactics_to_indices(tactics)
    idx_opp = tactics_to_indices(PRESETS["Balanced"])

    @st.cache_data(show_spinner=False)
    def compute_group_and_knockout(t: Tactics) -> tuple[dict, dict]:
        group_outcome = simulate_group_monte_carlo(
            teams=teams,
            group_codes=group_codes,
            korea_code=korea_code,
            korea_tactics=t,
            n=1000,
            seed=42,
        )
        tournament_outcome = simulate_tournament_path_monte_carlo(
            teams=teams,
            korea_code=korea_code,
            korea_tactics=t,
            tournament_json=tournament,
            group_codes=group_codes,
            n=1000,
            seed=9,
        )
        return group_outcome.__dict__, tournament_outcome.__dict__

    group_dict, tourn_dict = compute_group_and_knockout(tactics)

    korea = _make_team_strength(teams, "KOR")
    mex = _make_team_strength(teams, "MEX")
    sui = _make_team_strength(teams, "SUI")
    sen = _make_team_strength(teams, "SEN")
    opponents = {"MEX": mex, "SUI": sui, "SEN": sen}
    korea_fixtures = tournament["group_stage"]["korea_fixtures"]

    match_results: dict[str, dict] = {}
    for fx in korea_fixtures:
        opp_code = fx["away"]
        opp = opponents[opp_code]
        dist = simulate_match_distribution(korea, opp, indices, opp_idx=idx_opp)
        match_results[fx["match_id"]] = {"opp_code": opp_code, "dist": dist}

    expected_avg_goals_for = sum(m["dist"].exp_goals_for for m in match_results.values()) / 3.0
    expected_avg_goals_against = sum(m["dist"].exp_goals_against for m in match_results.values()) / 3.0

    expected_points = sum(
        _expected_points_from_wdl(m["dist"].win_prob, m["dist"].draw_prob, m["dist"].loss_prob) for m in match_results.values()
    )

    qualify_prob = float(group_dict["qualify_prob"])
    r16_prob = float(tourn_dict["path_probs"].get("R16", 0.0))

    st.title("대한민국 2026 월드컵 전술 시뮬레이터")
    st.caption("설명 가능한 확률 기반 데모입니다. 실제 예측이 아니라, 전술 입력이 확률/기대 득점에 미치는 영향을 보여줍니다.")

    tabs = st.tabs(["Overview", "Match Simulation", "Tournament Path", "Tactical Analysis"])

    with tabs[0]:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("예상 승점", f"{expected_points:.1f}", help="조별리그 3경기 기대 승점(W/D/L 기반).")
        c2.metric("조 통과 확률", _format_prob(qualify_prob))
        c3.metric("16강 진출 확률", _format_prob(r16_prob))
        c4.metric("평균 득점", f"{expected_avg_goals_for:.2f}")
        c5.metric("평균 실점", f"{expected_avg_goals_against:.2f}")

        st.divider()

        left, right = st.columns([1.1, 0.9])

        with left:
            st.subheader("조별리그 경기 카드 (대한민국)")
            for fx in korea_fixtures:
                mid = fx["match_id"]
                opp_code = match_results[mid]["opp_code"]
                dist = match_results[mid]["dist"]
                most_gf, most_ga = dist.most_likely_score

                st.markdown(f"### {opp_code}전")
                c_win, c_draw, c_loss = st.columns(3)
                c_win.metric("승", _format_prob(dist.win_prob))
                c_draw.metric("무", _format_prob(dist.draw_prob))
                c_loss.metric("패", _format_prob(dist.loss_prob))
                st.caption(
                    f"기대 득점/실점: {dist.exp_goals_for:.2f} / {dist.exp_goals_against:.2f}  · 예상 스코어(최빈): {most_gf}-{most_ga}"
                )
                st.plotly_chart(match_score_heatmap(dist, title=f"{opp_code}전 예상 스코어 분포(0~5골)"), use_container_width=True)
                st.divider()

        with right:
            st.subheader("레이더 차트 (팀 전술 프로파일)")
            st.plotly_chart(radar_tactical_indices(indices), use_container_width=True)

            st.subheader("현재 설정 요약")
            st.write(f"- 포메이션: `{tactics.formation}`")
            st.write(f"- 리스크 성향: `{tactics.risk_profile}`")
            st.write(f"- 압박/라인: `{tactics.pressing}` / `{tactics.line_height}`")
            st.write(f"- 점유/직선성: `{tactics.possession}` / `{tactics.directness}`")
            st.write(f"- 측면/세트피스: `{tactics.wing_focus}` / `{tactics.set_piece_focus}`")
            st.write(f"- 로테이션/에이스: `{tactics.rotation}` / `{tactics.ace_dependency}`")

        st.divider()
        st.subheader("조별 순위 확률")
        rank_probs = {int(k): float(v) for k, v in group_dict["rank_probs"].items()}
        table_rows = []
        for r in [1, 2, 3, 4]:
            table_rows.append(
                {
                    "순위": r,
                    "확률": round(rank_probs.get(r, 0.0) * 100.0, 2),
                    "비고": "진출" if r <= 2 else "",
                }
            )
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

        st.subheader("시나리오 요약")
        st.write(_scenario_summary(tactics, indices, group_qualify_prob=qualify_prob, r16_prob=r16_prob))

    with tabs[1]:
        st.subheader("Match Simulation 상세")
        st.caption("각 경기는 전술 인덱스와 팀 전력을 바탕으로 포아송 분포(0~5골)를 만들고 W/D/L과 기대 득점을 계산합니다.")
        for fx in korea_fixtures:
            mid = fx["match_id"]
            opp_code = match_results[mid]["opp_code"]
            dist = match_results[mid]["dist"]
            most_gf, most_ga = dist.most_likely_score

            st.markdown(f"## {opp_code}전")
            st.plotly_chart(match_score_heatmap(dist), use_container_width=True)
            st.write({"승": _format_prob(dist.win_prob), "무": _format_prob(dist.draw_prob), "패": _format_prob(dist.loss_prob)})
            st.write(f"가장 가능성 높은 스코어: `{most_gf}-{most_ga}`")

    with tabs[2]:
        st.subheader("Tournament Path")
        path_probs = {k: float(v) for k, v in tourn_dict["path_probs"].items()}
        st.plotly_chart(tournament_path_bar(path_probs), use_container_width=True)
        st.write("R32부터 단판 토너먼트로 진행하며 무승부는 변동성(전술 인덱스)에 약간 더 민감하게 동전결정합니다(데모 규칙).")

    with tabs[3]:
        st.subheader("Tactical Analysis")
        st.write("전술 입력값은 `전술 → 팀 지수`로 변환되고, 지수는 기대 득점/실점과 변동성(리스크)에 영향을 줍니다.")
        st.plotly_chart(radar_tactical_indices(indices, title="팀 전술 프로파일(Effective Indices)"), use_container_width=True)
        st.divider()
        st.write(
            "핵심 트레이드오프(데모 모델): `압박↑`은 공격↑/체력↓/리스크↑, `라인↑`은 압박↑ 및 뒷공간 리스크(수비↓)/변동성↑, `점유↑`는 안정성↑(수비·미드필드↑)지만 전환 속도↓."
        )
        st.write(f"현재 계산된 변동성(리스크) 인덱스: `{indices.volatility:.1f}`")
        st.warning("이 시뮬레이터는 축구 엔진이 아닙니다. 입력→지수→확률로 연결되는 ‘설명 가능한 데모’에 초점을 둡니다.")


if __name__ == "__main__":
    main()

 # from __future__ import annotations  # legacy tail (keep commented to avoid SyntaxError)

import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from src.charts import match_score_heatmap, radar_tactical_indices, tournament_path_bar
from src.simulator import sample_score_from_matrix, simulate_match_distribution
from src.tactics import PRESETS, Formation, RiskProfile, Tactics, TeamIndices, tactics_to_indices
from src.tournament import simulate_group_monte_carlo, simulate_tournament_path_monte_carlo


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


@st.cache_data(show_spinner=False)
def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load_teams() -> dict:
    return load_json(DATA_DIR / "teams.json")


@st.cache_data(show_spinner=False)
def load_tournament() -> dict:
    return load_json(DATA_DIR / "tournament_2026.json")


def _make_team_strength(teams: dict, code: str):
    # Keep this light: we only need ratings for the simulator.
    from src.simulator import TeamStrength

    t = teams[code]
    return TeamStrength(
        code=code,
        name=t["name"],
        attack=float(t["attack"]),
        defense=float(t["defense"]),
        midfield=float(t["midfield"]),
        transition=float(t["transition"]),
        stamina=float(t["stamina"]),
    )


def _expected_points_from_wdl(win: float, draw: float, loss: float) -> float:
    return 3.0 * win + 1.0 * draw + 0.0 * loss


def _format_prob(p: float) -> str:
    return f"{p * 100:.1f}%"


def _scenario_summary(t: Tactics, indices: TeamIndices, group_qualify_prob: float, r16_prob: float) -> str:
    # Translate the requested knobs into readable, explainable statements.
    press = t.pressing
    line = t.line_height
    poss = t.possession
    direct = t.directness
    wing = t.wing_focus
    risk = t.risk_profile
    vol = indices.volatility

    statements: list[str] = []

    # 1) Risk / volatility
    if vol >= 62:
        statements.append("현재 설정은 `리스크(변동성)`가 큰 편이라, 결과가 흔들릴 가능성이 큽니다.")
    elif vol <= 40:
        statements.append("현재 설정은 `리스크(변동성)`가 낮아, 점수 격차가 비교적 안정적으로 수렴하는 경향입니다.")
    else:
        statements.append("현재 설정은 `리스크(변동성)`가 중간 수준으로, 공격과 안정의 균형이 잡힌 편입니다.")

    # 2) Pressing / line trade-offs
    if press >= 70 and line >= 65:
        statements.append("`압박`과 `수비 라인 높이`를 함께 높이면, 상대를 밀어붙이지만 뒷공간 리스크가 동반됩니다.")
    elif press >= 70 and line < 45:
        statements.append("`압박`을 높였지만 라인을 낮추면, 공수 균형은 좋아지되 공격 전환의 스파이크가 줄어들 수 있습니다.")
    elif press < 40 and line >= 65:
        statements.append("`압박`은 낮고 라인은 높으면, 점유를 빼앗길 때 전환 실점 가능성이 커질 수 있습니다.")
    else:
        statements.append("현재 압박/라인 조합은 데모 모델 기준으로 공수 간 충돌이 비교적 완만한 편입니다.")

    # 3) Possession / directness
    if poss >= 65 and direct >= 65:
        statements.append("`점유`와 `직선성`을 같이 높이면, 경기 주도는 하면서도 기회는 빠르게 만들 가능성이 있습니다.")
    elif poss >= 65:
        statements.append("`점유 지향`이 높아 수비 안정성과 경기 흐름 제어가 커지지만, 전환 속도/속도감은 둔해질 수 있습니다.")
    elif direct >= 65:
        statements.append("`공격 직선성`이 높아 역습/전환 찬스가 늘지만, 득점이 들쑥날쑥해질 수 있습니다.")

    # 4) Risk profile
    if risk == "보수":
        statements.append("`보수` 성향은 기대 득점보다 안정(실점 억제)을 우선시하는 쪽으로 인덱스를 조정합니다.")
    elif risk == "공격":
        statements.append("`공격` 성향은 기대 득점 상단을 키우는 대신 변동성을 동반하는 방향입니다.")
    else:
        statements.append("`균형` 성향은 공격/수비 트레이드오프를 완만하게 반영합니다.")

    # 5) Outcomes
    statements.append(f"조 통과 확률(상위 2): {_format_prob(group_qualify_prob)}")
    statements.append(f"16강 진출 확률: {_format_prob(r16_prob)}")

    return " ".join(statements)


def main() -> None:
    st.set_page_config(page_title="대한민국 2026 월드컵 전술 시뮬레이터", layout="wide", initial_sidebar_state="expanded")

    teams = load_teams()
    tournament = load_tournament()

    # --- Sidebar: tactical inputs ---
    st.sidebar.header("전술 입력")

    preset_names = list(PRESETS.keys())
    preset = st.sidebar.selectbox("프리셋", preset_names, index=0)

    # Initialize session state once.
    default_t = PRESETS[preset]
    if "tactics_state" not in st.session_state:
        st.session_state["tactics_state"] = {
            "formation": default_t.formation,
            "pressing": default_t.pressing,
            "line_height": default_t.line_height,
            "possession": default_t.possession,
            "directness": default_t.directness,
            "wing_focus": default_t.wing_focus,
            "set_piece_focus": default_t.set_piece_focus,
            "rotation": default_t.rotation,
            "ace_dependency": default_t.ace_dependency,
            "risk_profile": default_t.risk_profile,
        }

    def apply_preset():
        t = PRESETS[preset]
        st.session_state["tactics_state"].update(
            {
                "formation": t.formation,
                "pressing": t.pressing,
                "line_height": t.line_height,
                "possession": t.possession,
                "directness": t.directness,
                "wing_focus": t.wing_focus,
                "set_piece_focus": t.set_piece_focus,
                "rotation": t.rotation,
                "ace_dependency": t.ace_dependency,
                "risk_profile": t.risk_profile,
            }
        )
        st.rerun()

    if st.sidebar.button("프리셋 적용"):
        apply_preset()

    ts = st.session_state["tactics_state"]

    st.sidebar.divider()

    formation = st.sidebar.selectbox(
        "포메이션",
        ["4-2-3-1", "4-3-3", "3-4-3", "4-4-2"],
        index=["4-2-3-1", "4-3-3", "3-4-3", "4-4-2"].index(ts["formation"]),
    )
    pressing = st.sidebar.slider("압박 강도", 0, 100, int(ts["pressing"]))
    line_height = st.sidebar.slider("수비 라인 높이", 0, 100, int(ts["line_height"]))
    possession = st.sidebar.slider("점유율 지향도", 0, 100, int(ts["possession"]))
    directness = st.sidebar.slider("공격 직선성", 0, 100, int(ts["directness"]))
    wing_focus = st.sidebar.slider("측면 활용 비중", 0, 100, int(ts["wing_focus"]))
    set_piece_focus = st.sidebar.slider("세트피스 집중도", 0, 100, int(ts["set_piece_focus"]))
    rotation = st.sidebar.slider("로테이션 강도", 0, 100, int(ts["rotation"]))
    ace_dependency = st.sidebar.slider("에이스 의존도", 0, 100, int(ts["ace_dependency"]))
    risk_profile = st.sidebar.selectbox("리스크 성향", ["보수", "균형", "공격"], index=["보수", "균형", "공격"].index(ts["risk_profile"]))

    # Update session snapshot so toggling sliders doesn't require apply.
    ts.update(
        {
            "formation": formation,
            "pressing": pressing,
            "line_height": line_height,
            "possession": possession,
            "directness": directness,
            "wing_focus": wing_focus,
            "set_piece_focus": set_piece_focus,
            "rotation": rotation,
            "ace_dependency": ace_dependency,
            "risk_profile": risk_profile,
        }
    )

    korea_code = "KOR"
    group_codes = ["KOR", "MEX", "SUI", "SEN"]

    # --- Build tactics object ---
    tactics = Tactics(
        formation=formation,  # type: ignore[arg-type]
        pressing=int(pressing),
        line_height=int(line_height),
        possession=int(possession),
        directness=int(directness),
        wing_focus=int(wing_focus),
        set_piece_focus=int(set_piece_focus),
        rotation=int(rotation),
        ace_dependency=int(ace_dependency),
        risk_profile=risk_profile,  # type: ignore[arg-type]
    )

    indices = tactics_to_indices(tactics)
    idx_opp = tactics_to_indices(PRESETS["Balanced"])

    # --- Run simulations (cached) ---
    @st.cache_data(show_spinner=False)
    def compute_group_and_knockout(t: Tactics) -> tuple[dict, dict]:
        group_outcome = simulate_group_monte_carlo(
            teams=teams,
            group_codes=group_codes,
            korea_code=korea_code,
            korea_tactics=t,
            n=1000,
            seed=42,
        )
        tournament_outcome = simulate_tournament_path_monte_carlo(
            teams=teams,
            korea_code=korea_code,
            korea_tactics=t,
            tournament_json=tournament,
            group_codes=group_codes,
            n=1000,
            seed=9,
        )
        return group_outcome.__dict__, tournament_outcome.__dict__

    group_dict, tourn_dict = compute_group_and_knockout(tactics)
    group_outcome = type("GroupOutcomeShim", (), group_dict)
    tourn_outcome = type("TournamentOutcomeShim", (), tourn_dict)

    # --- Korea match simulation cards ---
    korea = _make_team_strength(teams, "KOR")
    mex = _make_team_strength(teams, "MEX")
    sui = _make_team_strength(teams, "SUI")
    sen = _make_team_strength(teams, "SEN")
    opponents = {"MEX": mex, "SUI": sui, "SEN": sen}
    korea_fixtures = tournament["group_stage"]["korea_fixtures"]

    match_results = {}
    for fx in korea_fixtures:
        opp_code = fx["away"]
        opp = opponents[opp_code]
        dist = simulate_match_distribution(korea, opp, indices, opp_idx=idx_opp)
        match_results[fx["match_id"]] = {"opp_code": opp_code, "dist": dist}

    expected_avg_goals_for = sum(m["dist"].exp_goals_for for m in match_results.values()) / 3.0
    expected_avg_goals_against = sum(m["dist"].exp_goals_against for m in match_results.values()) / 3.0

    # Expected points from W/D/L probabilities (more direct than group Monte Carlo average)
    expected_points = sum(
        _expected_points_from_wdl(m["dist"].win_prob, m["dist"].draw_prob, m["dist"].loss_prob) for m in match_results.values()
    )

    qualify_prob = float(group_dict["qualify_prob"])
    r16_prob = float(tourn_dict["path_probs"].get("R16", 0.0))

    # --- Tabs ---
    st.title("대한민국 2026 월드컵 전술 시뮬레이터")
    st.caption("설명 가능한 확률 기반 데모입니다. 실제 예측이 아니라, 전술 입력이 확률/기대 득점에 미치는 영향을 보여줍니다.")

    tabs = st.tabs(["Overview", "Match Simulation", "Tournament Path", "Tactical Analysis"])

    with tabs[0]:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("예상 승점", f"{expected_points:.1f}", help="조별리그 3경기 기대 승점(W/D/L 기반).")
        c2.metric("조 통과 확률", _format_prob(qualify_prob))
        c3.metric("16강 진출 확률", _format_prob(r16_prob))
        c4.metric("평균 득점", f"{expected_avg_goals_for:.2f}")
        c5.metric("평균 실점", f"{expected_avg_goals_against:.2f}")

        st.divider()

        left, right = st.columns([1.1, 0.9])

        with left:
            st.subheader("조별리그 경기 카드 (대한민국)")
            for fx in korea_fixtures:
                mid = fx["match_id"]
                opp_code = match_results[mid]["opp_code"]
                dist = match_results[mid]["dist"]
                most_gf, most_ga = dist.most_likely_score
                st.markdown(f"### {opp_code}전")
                c_win, c_draw, c_loss = st.columns(3)
                c_win.metric("승", _format_prob(dist.win_prob))
                c_draw.metric("무", _format_prob(dist.draw_prob))
                c_loss.metric("패", _format_prob(dist.loss_prob))

                st.caption(f"기대 득점/실점: {dist.exp_goals_for:.2f} / {dist.exp_goals_against:.2f}  · 예상 스코어(최빈): {most_gf}-{most_ga}")
                heat = match_score_heatmap(dist, title=f"{opp_code}전 예상 스코어 분포(0~5골)")
                st.plotly_chart(heat, use_container_width=True)
                st.divider()

        with right:
            st.subheader("레이더 차트 (팀 전술 프로파일)")
            st.plotly_chart(radar_tactical_indices(indices), use_container_width=True)

            st.subheader("현재 설정 요약")
            st.write(f"- 포메이션: `{tactics.formation}`")
            st.write(f"- 리스크 성향: `{tactics.risk_profile}`")
            st.write(f"- 압박/라인: `{tactics.pressing}` / `{tactics.line_height}`")
            st.write(f"- 점유/직선성: `{tactics.possession}` / `{tactics.directness}`")
            st.write(f"- 측면/세트피스: `{tactics.wing_focus}` / `{tactics.set_piece_focus}`")
            st.write(f"- 로테이션/에이스: `{tactics.rotation}` / `{tactics.ace_dependency}`")

        st.divider()
        st.subheader("조별 순위 확률")
        rank_probs = {int(k): float(v) for k, v in group_dict["rank_probs"].items()}
        table_rows = []
        for r in [1, 2, 3, 4]:
            table_rows.append({"순위": r, "확률": round(rank_probs.get(r, 0.0) * 100.0, 2), "비고": "진출" if r <= 2 else ""})
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

        st.subheader("시나리오 요약")
        summary = _scenario_summary(tactics, indices, qualify_prob=qualify_prob, r16_prob=r16_prob)
        st.write(summary)

    with tabs[1]:
        st.subheader("Match Simulation 상세")
        st.caption("각 경기는 전술 인덱스와 팀 전력을 바탕으로 포아송 분포(0~5골)를 만들고, 그 분포로 W/D/L과 기대 득점을 계산합니다.")
        for fx in korea_fixtures:
            mid = fx["match_id"]
            opp_code = match_results[mid]["opp_code"]
            dist = match_results[mid]["dist"]
            most_gf, most_ga = dist.most_likely_score
            st.markdown(f"## {opp_code}전")
            st.plotly_chart(match_score_heatmap(dist), use_container_width=True)
            wdl = {
                "승": dist.win_prob,
                "무": dist.draw_prob,
                "패": dist.loss_prob,
            }
            st.write({k: _format_prob(v) for k, v in wdl.items()})
            st.write(f"가장 가능성 높은 스코어: `{most_gf}-{most_ga}`")

    with tabs[2]:
        st.subheader("Tournament Path")
        path_probs = {k: float(v) for k, v in tourn_dict["path_probs"].items()}
        st.plotly_chart(tournament_path_bar(path_probs), use_container_width=True)

        st.subheader("라운드별 의미")
        st.write("이 데모에서는 R32부터 단판 토너먼트로 진행하며, 무승부는 변동성(전술 인덱스)에 약간 더 민감하게 동전결정합니다.")

    with tabs[3]:
        st.subheader("Tactical Analysis")
        st.write("전술 입력값은 `전술 → 팀 지수`로 변환되고, 지수는 기대 득점/실점과 변동성(리스크)에 영향을 줍니다.")
        st.plotly_chart(radar_tactical_indices(indices, title="팀 전술 프로파일(Effective Indices)"), use_container_width=True)

        st.divider()
        st.subheader("효과 요약(모델 해석 포인트)")
        st.write(
            "핵심 트레이드오프(데모 모델): `압박↑`은 공격↑/체력↓/리스크↑, `라인↑`은 압박↑ 및 뒷공간 리스크(수비↓)/변동성↑, `점유↑`는 안정성↑(수비·미드필드↑)지만 전환 속도↓."
        )
        st.write(f"현재 계산된 변동성(리스크) 인덱스: `{indices.volatility:.1f}`")

        st.divider()
        st.subheader("설명 가능성을 위한 주의")
        st.warning("이 시뮬레이터는 축구 엔진이 아닙니다. 입력→지수→확률로 연결되는 ‘설명 가능한 데모’에 초점을 둡니다.")


# if __name__ == "__main__":
#     main()

"""
AI 편향 거울 (교육용 시뮬레이터)
==============================
단편적 입력만으로 자동 추론이 어떻게 구성될 수 있는지 보여주는 데모입니다.
실제 사람의 능력·정체성·가치를 판정하지 않으며, 외부 API를 사용하지 않습니다.
"""

# from __future__ import annotations  # legacy tail (keep commented to avoid SyntaxError)

import math
import re
from dataclasses import dataclass, field
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# 상수: 직업군·성향·키워드 매핑 (규칙 기반 시뮬레이션)
# ---------------------------------------------------------------------------

JOB_LABELS: tuple[str, ...] = (
    "개발/데이터",
    "디자인/예술",
    "교육/연구",
    "경영/금융",
    "미디어/콘텐츠",
    "돌봄/상담",
    "스포츠/활동",
)

TRAIT_LABELS: tuple[str, ...] = (
    "분석적",
    "창의적",
    "사교적",
    "차분함",
    "리더형",
    "꼼꼼함",
    "모험지향",
    "공감형",
)

# 소개/관심사 텍스트 → 직업군 가중 (content 신호)
JOB_KEYWORDS: dict[str, tuple[str, ...]] = {
    "개발/데이터": (
        "코드",
        "프로그래밍",
        "python",
        "파이썬",
        "데이터",
        "머신러닝",
        "딥러닝",
        "알고리즘",
        "github",
        "git",
        "컴퓨터",
        "공학",
        "전공",
        "sql",
        "분석",
        "통계",
        "모델링",
    ),
    "디자인/예술": (
        "디자인",
        "ui",
        "ux",
        "그림",
        "드로잉",
        "일러스트",
        "전시",
        "예술",
        "시각",
        "색",
        "타이포",
        "브랜딩",
        "창작",
    ),
    "교육/연구": (
        "교육",
        "강의",
        "연구",
        "논문",
        "학생",
        "봉사",
        "아동",
        "학습",
        "멘토",
        "독서",
        "도서관",
    ),
    "경영/금융": (
        "투자",
        "스타트업",
        "경영",
        "재무",
        "비즈니스",
        "전략",
        "vc",
        "펀딩",
        "매출",
        "마케팅",
    ),
    "미디어/콘텐츠": (
        "유튜브",
        "콘텐츠",
        "미디어",
        "영상",
        "방송",
        "팟캐스트",
        "글쓰기",
        "스토리",
    ),
    "돌봄/상담": (
        "상담",
        "돌봄",
        "공감",
        "심리",
        "케어",
        "코칭",
        "청취",
    ),
    "스포츠/활동": (
        "운동",
        "팀",
        "축구",
        "농구",
        "마라톤",
        "피트니스",
        "체력",
        "활동",
        "레저",
        "스포츠",
    ),
}

# 소개/관심사 → 성향 키워드
TRAIT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "분석적": ("분석", "데이터", "통계", "논리", "실험", "검증"),
    "창의적": ("창작", "아이디어", "디자인", "예술", "새로운"),
    "사교적": ("팀", "협업", "네트워킹", "발표", "소통"),
    "차분함": ("차분", "신중", "계획", "독서", "명상"),
    "리더형": ("리드", "주도", "기획", "운영", "책임"),
    "꼼꼼함": ("꼼꼼", "체크", "문서", "품질", "세부"),
    "모험지향": ("도전", "여행", "새로운", "스타트업", "실험"),
    "공감형": ("공감", "돌봄", "봉사", "상담", "아동"),
}

# 연상 이미지 태그 (텍스트 기반, 단정 아님)
TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "텍스트·코드": ("코드", "데이터", "분석", "프로그래밍"),
    "시각·콘텐츠": ("디자인", "영상", "콘텐츠", "그림"),
    "사람·관계": ("교육", "봉사", "팀", "상담"),
    "몸·활동": ("운동", "스포츠", "체력"),
    "숫자·전략": ("투자", "경영", "전략", "재무"),
}

# 이름 형식만 반영하는 매우 약한 보조 신호 (민감 속성 추정 금지)
# 가중치는 전체 대비 매우 작게 유지
NAME_FORMAT_WEIGHT = 0.08  # bias_score에 곱해 전체 스케일 조절


@dataclass
class AnalysisResult:
    """단일 입력에 대한 시뮬레이션 결과."""

    job_scores: dict[str, float]
    trait_scores: dict[str, float]
    association_tags: list[str]
    pseudo_confidence: float  # 실제 신뢰도 아님
    content_score: float
    bias_score: float
    generalization_risk: float  # 0~100
    bias_breakdown: dict[str, float]
    clue_effects: list[tuple[str, str]]  # (단서, 영향 요약)
    name_format_note: str
    soft_explanations: list[str]


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _token_hits(text: str, keywords: tuple[str, ...]) -> int:
    t = _normalize_text(text)
    n = 0
    for kw in keywords:
        if kw.lower() in t:
            n += 1
    return n


def analyze_name_format_only(name: str) -> tuple[str, float]:
    """
    이름 문자열의 표기 형식만 분류 (민감한 속성 추정 없음).
    반환: (설명 문구, 0~1 정규화된 형식적 신호 강도)
    """
    raw = (name or "").strip()
    if not raw:
        return "이름 입력 없음 — 표기 형식 신호는 적용되지 않습니다.", 0.0

    hangul = len(re.findall(r"[가-힣]", raw))
    latin = len(re.findall(r"[A-Za-z]", raw))
    total_letters = hangul + latin
    if total_letters == 0:
        return "문자 형식이 불명확합니다 — 표기 형식 신호는 매우 약하게만 반영됩니다.", 0.15

    ratio_h = hangul / max(total_letters, 1)
    ratio_l = latin / max(total_letters, 1)

    # 매우 약한 스칼라: '형식적 차이'만 표현
    if ratio_h >= 0.6:
        note = "한글 표기 비중이 큰 이름 형식 — 시뮬레이션상 아주 약한 형식 신호만 추가됩니다."
        strength = 0.25
    elif ratio_l >= 0.6:
        note = "라틴 문자 표기 비중이 큰 이름 형식 — 시뮬레이션상 아주 약한 형식 신호만 추가됩니다."
        strength = 0.25
    elif ratio_h > 0 and ratio_l > 0:
        note = "한글·라틴이 혼합된 표기 — 형식 신호는 참고용 수준으로만 반영됩니다."
        strength = 0.2
    else:
        note = "짧거나 단순한 표기 — 형식 신호는 거의 영향을 주지 않도록 설정했습니다."
        strength = 0.12

    return note, strength * NAME_FORMAT_WEIGHT


def score_content(intro: str, interests: str) -> tuple[dict[str, float], dict[str, float], list[str], list[tuple[str, str]]]:
    """자기소개·관심사에서 직업/성향/태그 점수."""
    blob = f"{intro}\n{interests}"
    jobs: dict[str, float] = {j: 0.0 for j in JOB_LABELS}
    traits: dict[str, float] = {t: 0.0 for t in TRAIT_LABELS}
    clues: list[tuple[str, str]] = []

    for job, kws in JOB_KEYWORDS.items():
        hits = _token_hits(blob, kws)
        if hits:
            jobs[job] += hits * 10.0
            clues.append((f"텍스트 단서({job} 관련 어휘)", f"직업군 후보 점수에 기여(시뮬레이션)"))

    for trait, kws in TRAIT_KEYWORDS.items():
        hits = _token_hits(blob, kws)
        if hits:
            traits[trait] += hits * 8.0
            clues.append((f"텍스트 단서({trait} 연상 어휘)", f"성향 키워드 점수에 기여(시뮬레이션)"))

    tags: list[str] = []
    for tag, kws in TAG_KEYWORDS.items():
        if _token_hits(blob, kws) > 0:
            tags.append(tag)

    if not tags:
        tags = ["단서가 제한적 — 연상 태그는 불확실할 수 있음"]

    # 텍스트 길이에 따른 과대 일반화 위험 힌트
    if len(_normalize_text(blob)) < 30:
        clues.append(("짧은 텍스트", "추론 불확실성이 커질 수 있음(시뮬레이션)"))

    return jobs, traits, tags, clues


def apply_name_format_nudge(
    jobs: dict[str, float],
    traits: dict[str, float],
    name_strength: float,
    debias: bool,
) -> tuple[dict[str, float], dict[str, float], float]:
    """
    이름 형식 신호는 매우 약하게만 섞음. debias True면 0.
    민감 속성이 아닌 '형식'에 대한 균등한 미세 요동만 부여.
    """
    if debias or name_strength <= 0:
        return jobs, traits, 0.0

    # 해시 기반 결정적 미세 요동 (특정 집단을 지칭하지 않음)
    bias_mag = name_strength * 3.0  # 최대 몇 점 미만
    out_j = dict(jobs)
    out_t = dict(traits)
    for k in out_j:
        # 직업 라벨 문자열 길이로만 미세 변동 — 임의이지만 재현 가능
        delta = (len(k) % 5 - 2) * bias_mag * 0.2
        out_j[k] = max(0.0, out_j[k] + delta)
    for k in out_t:
        delta = (len(k) % 7 - 3) * bias_mag * 0.15
        out_t[k] = max(0.0, out_t[k] + delta)

    return out_j, out_t, bias_mag


def compute_scores(
    name: str,
    intro: str,
    interests: str,
    age_band: str,
    debias: bool,
) -> AnalysisResult:
    jobs, traits, tags, clue_effects = score_content(intro, interests)
    name_note, name_strength = analyze_name_format_only(name)

    j2, t2, bias_mag = apply_name_format_nudge(jobs, traits, name_strength, debias)

    # content vs bias 분해
    content_vec = sum(jobs.values()) + sum(traits.values()) * 0.5
    bias_vec = 0.0 if debias else bias_mag * 10.0 + name_strength * 5.0

    # 편향 유형별 (시뮬레이션 지표)
    text_richness = min(1.0, len(_normalize_text(intro + interests)) / 400.0)
    name_bias = 0.0 if debias else min(100.0, name_strength * 120.0)
    job_stereotype = min(100.0, max(j2.values()) / max(max(j2.values(), default=1), 1) * 35.0 + (1.0 - text_richness) * 25.0)
    personality_general = min(100.0, max(t2.values(), default=0) / max(max(t2.values(), default=1), 1) * 30.0 + 15.0)
    culture_lang = min(100.0, (1.0 - text_richness) * 40.0 + _token_hits(intro + interests, ("영어", "english", "해외", "글로벌")) * 5.0)

    breakdown = {
        "이름 표기 형식 신호(참고)": name_bias,
        "직업 일반화 가능성(시뮬)": job_stereotype,
        "성향 일반화 가능성(시뮬)": personality_general,
        "짧은 단서·언어 혼합 등(시뮬)": culture_lang,
    }

    gen_risk = float(
        min(
            100.0,
            0.22 * name_bias + 0.28 * job_stereotype + 0.28 * personality_general + 0.22 * culture_lang,
        )
    )

    # 의사 신뢰도 (실제 아님)
    pseudo = min(0.95, 0.35 + 0.45 * text_richness + (0.02 if not debias else 0.0))
    pseudo = max(0.2, pseudo - gen_risk / 500.0)

    soft: list[str] = []
    soft.append("이 화면의 수치는 **실제 신뢰도가 아니라** 시뮬레이션상의 '자동 태깅이 확신하는 듯 보이는 정도'를 흉내 낸 것입니다.")
    if age_band and age_band != "(선택 안 함)":
        soft.append("연령대는 데모 입력일 뿐이며, 어떤 능력이나 성격도 단정하지 않습니다.")
    if not debias and name_bias > 8:
        soft.append("이번 결과는 **텍스트 단서 외에** 이름 **표기 형식**에서 오는 아주 작은 가중(시뮬)이 섞였을 수 있습니다.")
    elif debias:
        soft.append("편향 제거 모드에서는 이름 표기 관련 가중을 빼고, 텍스트 단서 위주로만 계산했습니다.")
    if text_richness < 0.3:
        soft.append("입력이 짧을수록 모델이 빈칸을 **추측으로 채울** 여지가 커질 수 있습니다(시뮬레이션 관점).")
    else:
        soft.append("관심사·소개 문장이 비교적 구체적이라, 직업군 연상은 **상대적으로 단서에 가깝게** 보일 수 있습니다. 그래도 성향 일반화는 과할 수 있습니다.")

    return AnalysisResult(
        job_scores=j2,
        trait_scores=t2,
        association_tags=tags,
        pseudo_confidence=pseudo,
        content_score=float(content_vec),
        bias_score=float(bias_vec),
        generalization_risk=gen_risk,
        bias_breakdown=breakdown,
        clue_effects=clue_effects[:12],
        name_format_note=name_note,
        soft_explanations=soft,
    )


def top_n(d: dict[str, float], n: int) -> list[tuple[str, float]]:
    return sorted(d.items(), key=lambda x: x[1], reverse=True)[:n]


def build_fig_jobs_bar(result: AnalysisResult, title: str) -> go.Figure:
    top = top_n(result.job_scores, 3)
    labels = [x[0] for x in top]
    vals = [max(0.0, x[1]) for x in top]
    fig = go.Figure(go.Bar(x=vals, y=labels, orientation="h", marker_color="#5B8DEF"))
    fig.update_layout(
        title=title,
        margin=dict(l=10, r=10, t=40, b=10),
        height=280,
        xaxis_title="시뮬레이션 점수(임의 단위)",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def build_fig_bias_radar(breakdown: dict[str, float], title: str) -> go.Figure:
    cats = list(breakdown.keys())
    vals = [float(breakdown[k]) for k in cats]
    fig = go.Figure(
        go.Scatterpolar(
            r=vals + [vals[0]],
            theta=cats + [cats[0]],
            fill="toself",
            name="편향 가능성 지표",
            line_color="#E07A5F",
        )
    )
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        title=title,
        margin=dict(l=30, r=30, t=50, b=10),
        height=360,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def build_fig_gauge(risk: float, title: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=min(100.0, max(0.0, risk)),
            title={"text": title},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#6C757D"},
                "steps": [
                    {"range": [0, 40], "color": "#E9ECEF"},
                    {"range": [40, 70], "color": "#DEE2E6"},
                    {"range": [70, 100], "color": "#CED4DA"},
                ],
            },
        )
    )
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=40, b=10))
    return fig


def build_fig_content_bias_stacked(c: float, b: float, title: str) -> go.Figure:
    total = max(c + b, 1e-6)
    fig = go.Figure(
        go.Bar(
            name="텍스트 단서 기여(시뮬)",
            x=[c / total * 100],
            y=["구성"],
            orientation="h",
            marker_color="#81C784",
        )
    )
    fig.add_trace(
        go.Bar(
            name="표기·형식 등 편향 신호(시뮬)",
            x=[b / total * 100],
            y=["구성"],
            orientation="h",
            marker_color="#FFB74D",
        )
    )
    fig.update_layout(
        barmode="stack",
        title=title,
        xaxis=dict(title="비중(%)", range=[0, 100]),
        showlegend=True,
        height=220,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig


def build_fig_compare_jobs(r1: AnalysisResult, r2: AnalysisResult, la: str, lb: str) -> go.Figure:
    jobs = JOB_LABELS
    fig = go.Figure()
    fig.add_trace(go.Bar(name=la, x=list(jobs), y=[r1.job_scores[j] for j in jobs], marker_color="#5B8DEF"))
    fig.add_trace(go.Bar(name=lb, x=list(jobs), y=[r2.job_scores[j] for j in jobs], marker_color="#9575CD"))
    fig.update_layout(
        barmode="group",
        title="직업군 연상 점수 비교(시뮬레이션)",
        xaxis_tickangle=-35,
        height=400,
        margin=dict(l=10, r=10, t=50, b=80),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def inject_presentation_css() -> None:
    st.markdown(
        """
        <style>
        .block-card {
            border: 1px solid #e6e6e6;
            border-radius: 12px;
            padding: 1rem 1.25rem;
            background: #fafafa;
            margin-bottom: 0.75rem;
        }
        .section-title {
            font-size: 1.15rem;
            font-weight: 650;
            margin: 0 0 0.35rem 0;
            color: #222;
        }
        .hint {
            font-size: 0.92rem;
            color: #555;
            margin-bottom: 0.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def card(title: str, hint: str | None = None) -> None:
    st.markdown(f'<div class="block-card"><p class="section-title">{title}</p>', unsafe_allow_html=True)
    if hint:
        st.markdown(f'<p class="hint">{hint}</p>', unsafe_allow_html=True)


def card_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


EXAMPLE_PROFILES: dict[str, dict[str, str]] = {
    "예시 1: 컴공·독서·데이터": {
        "name": "김서연",
        "intro": "컴퓨터공학을 전공했고, 독서 모임에서 데이터 관련 책을 자주 읽습니다.",
        "interests": "Python, 데이터 시각화, 독서",
    },
    "예시 2: 디자인·전시": {
        "name": "Lee Jordan",
        "intro": "시각디자인을 공부했고 전시 기획 동아리에서 활동했습니다.",
        "interests": "전시, 드로잉, 브랜딩",
    },
    "예시 3: 교육 봉사·아동": {
        "name": "박민호",
        "intro": "지역 아동센터에서 봉사하며 교육에 관심이 많습니다.",
        "interests": "봉사, 아동, 멘토링",
    },
    "예시 4: 스타트업·투자": {
        "name": "최아린",
        "intro": "스타트업에서 일하며 투자와 비즈니스 모델을 공부 중입니다.",
        "interests": "스타트업, 투자, 전략",
    },
    "예시 5: 운동·팀": {
        "name": "정다운",
        "intro": "팀 스포츠를 즐기고 체력 관리를 꾸준히 합니다.",
        "interests": "축구, 팀워크, 피트니스",
    },
}


def init_session() -> None:
    defaults = {
        "mode": "단일 분석",
        "debias": False,
        "age": "(선택 안 함)",
        "s_name": "",
        "s_intro": "",
        "s_interests": "",
        "c_name_a": "",
        "c_name_b": "",
        "c_intro_a": "",
        "c_intro_b": "",
        "c_int_a": "",
        "c_int_b": "",
        "example_key": "(선택 안 함)",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def render_single(debias: bool) -> None:
    st.subheader("1) 입력")
    st.caption("이름은 **표기 형식** 참고용으로만 쓰이며, 실제 정체성이나 능력을 추정하지 않습니다.")

    c1, c2 = st.columns([1, 2])
    with c1:
        name = st.text_input("이름", key="s_name", placeholder="예: 홍길동 또는 Alex Kim")
        age = st.selectbox(
            "연령대 (선택)",
            ["(선택 안 함)", "10대", "20대", "30대", "40대", "50대 이상"],
            key="age",
        )
    with c2:
        intro = st.text_area("자기소개", key="s_intro", height=140, placeholder="짧게라도 구체적인 단서를 넣어보세요.")
        interests = st.text_input("관심사/키워드 (쉼표로 구분)", key="s_interests", placeholder="예: 데이터, 봉사, 디자인")

    run = st.button("시뮬레이션 실행", type="primary", key="run_single")
    remove_name_btn = st.button("이름 제거 후 같은 내용으로 다시 보기", key="rm_name_single")

    auto_run = st.session_state.pop("auto_analyze_single", False)
    if remove_name_btn:
        st.session_state["s_name"] = ""
        st.session_state["auto_analyze_single"] = True
        st.rerun()

    if not run and not auto_run:
        return

    try:
        name = st.session_state.get("s_name", name)
        res = compute_scores(name, intro, interests, age, debias)
    except Exception as e:
        st.error(f"분석 중 문제가 발생했습니다: {e}")
        return

    st.divider()
    st.subheader("2) 핵심 요약")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("일반화 위험도(시뮬)", f"{res.generalization_risk:.0f}", help="0~100, 데모용 지표입니다.")
    m2.metric("텍스트 단서 점수(상대)", f"{res.content_score:.1f}")
    m3.metric("형식·편향 신호(상대)", f"{res.bias_score:.1f}")
    m4.metric("의사 신뢰도 흉내", f"{res.pseudo_confidence:.2f}", help="실제 신뢰도 아님")

    st.info(
        " ".join(res.soft_explanations[:2])
        + " 이 앱은 사람을 평가하지 않고, **자동 추론이 어떻게 조립될 수 있는지** 보여줍니다."
    )

    st.subheader("3) AI의 즉각적 추론 (시뮬레이션)")
    card("추정 직업군 상위 (데모)", "특정 직업에 대한 단정이 아니라, 키워드 매칭 기반 연상입니다.")
    jtop = top_n(res.job_scores, 3)
    for rank, (jn, sc) in enumerate(jtop, start=1):
        st.write(f"{rank}. **{jn}** — 연상 점수(임의 단위): {sc:.1f}")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(build_fig_jobs_bar(res, "직업군 Top 3 (막대)"), use_container_width=True)
    with c2:
        st.plotly_chart(
            build_fig_content_bias_stacked(res.content_score, res.bias_score, "텍스트 단서 vs 형식 신호 비중(시뮬)"),
            use_container_width=True,
        )
    card_end()

    card("추정 성향 키워드 상위 (데모)", "성격 판정이 아니라, 텍스트에서 자주 함께 등장하는 이미지를 흉내낸 것입니다.")
    ttop = top_n(res.trait_scores, 5)
    for rank, (tn, sc) in enumerate(ttop, start=1):
        st.write(f"{rank}. **{tn}** — {sc:.1f}")
    card_end()

    card("연상 이미지 태그", "사람의 본질을 설명하는 라벨이 아니라, 입력 문장에서 떠오를 수 있는 주제를 넓게 묶은 것입니다.")
    st.write(", ".join(f"`{t}`" for t in res.association_tags))
    card_end()

    st.caption(
        f"이름 표기 참고: {res.name_format_note} "
        "표기 형식 신호는 **의도적으로 매우 약한 가중치**로만 반영했습니다."
    )
    st.caption(
        "‘의사 신뢰도’는 실제 예측 정확도가 아니라, 시스템이 **마치 확신하는 듯** 보이는 UI 경향을 흉내 낸 값입니다."
    )

    st.subheader("4) 편향·일반화 분석 (시뮬레이션)")
    card("단서 → 영향(요약)", "어떤 입력이 점수에 기여했는지 대략적으로 나눈 것입니다.")
    for clue, eff in res.clue_effects[:8]:
        st.write(f"- **{clue}**: {eff}")
    card_end()

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(build_fig_bias_radar(res.bias_breakdown, "편향 유형별 가능성(시뮬)"), use_container_width=True)
    with c2:
        st.plotly_chart(build_fig_gauge(res.generalization_risk, "전체 일반화 위험도(시뮬)"), use_container_width=True)

    st.subheader("5) 해석 및 한계")
    with st.expander("이 결과를 어떻게 읽으면 좋을까요?", expanded=True):
        st.markdown(
            """
            - 숫자는 **교육용 시뮬레이션**이며, 실제 AI 서비스의 출력과 다릅니다.
            - 직업·성향은 **입력 문장의 단어**와 규칙 매칭으로 만든 **가상의 연상**입니다.
            - 이름은 **표기 형식**만 반영하며, 인종·국적·종교 등 민감 정보를 추정하지 않습니다.
            - 짧은 입력일수록 빈칸을 메우려는 **과한 일반화**가 늘어날 수 있습니다(시뮬 관점).
            """
        )

    st.subheader("6) 왜 이 앱이 필요한가")
    with st.expander("교육 목적 — 왜 이런 데모가 의미가 있나요?", expanded=False):
        st.markdown(
            """
            실제 서비스에서도 모델은 **아주 적은 단서**로 프로필을 ‘완성’하려는 경향이 있습니다.
            이 데모는 그 과정이 **얼마나 성급할 수 있는지**를 체험으로 보여 주기 위한 것입니다.
            특히 이름 표기 같은 **형식 신호**가, 내용과 섞일 때 해석이 흔들릴 수 있다는 점을
            발표·교육 맥락에서 함께 이야기하기 쉽게 만들었습니다.

            **이 앱이 하지 않는 것**: 실제 채용·신용·안전 판단, 개인의 가치·능력·정체성 평가.
            """
        )


def render_compare(debias: bool) -> None:
    st.subheader("비교 실험 — 두 입력을 나란히")
    st.caption(
        "같은 자기소개에 **이름만 다른 경우**를 빠르게 시험하거나, "
        "한쪽 이름을 비워 **텍스트만**으로 비교해 보세요. 모든 수치는 시뮬레이션입니다."
    )

    auto_cmp = st.session_state.pop("auto_compare", False)

    left, right = st.columns(2)
    with left:
        st.markdown("**좌측 프로필**")
        na = st.text_input("이름 A", key="c_name_a")
        ia = st.text_area("자기소개 A", key="c_intro_a", height=120)
        ta = st.text_input("관심사 A", key="c_int_a")
    with right:
        st.markdown("**우측 프로필**")
        nb = st.text_input("이름 B", key="c_name_b")
        ib = st.text_area("자기소개 B", key="c_intro_b", height=120)
        tb = st.text_input("관심사 B", key="c_int_b")

    st.markdown("**빠른 실험 (이름 표기는 매우 약한 신호로만 반영됩니다)**")
    q1, q2 = st.columns(2)
    with q1:
        sync_intro = st.button(
            "동일 자기소개·관심사: 좌측 내용을 우측에 복사 (이름 B는 유지)",
            key="sync_lr",
            help="이름만 다르고 소개는 같을 때의 차이를 보기 위한 준비 단계입니다.",
        )
    with q2:
        clear_names = st.button("양쪽 이름 비우고 자동 재비교", key="clear_names_btn")

    if sync_intro:
        st.session_state["c_intro_b"] = st.session_state.get("c_intro_a", "")
        st.session_state["c_int_b"] = st.session_state.get("c_int_a", "")
        st.rerun()
    if clear_names:
        st.session_state["c_name_a"] = ""
        st.session_state["c_name_b"] = ""
        st.session_state["auto_compare"] = True
        st.rerun()

    run_c = st.button("비교 시뮬레이션 실행", type="primary", key="run_cmp")

    if not run_c and not auto_cmp:
        st.info(
            "입력 후 **비교 시뮬레이션 실행**을 누르세요. "
            "위 버튼으로 **소개만 동일화**하거나 **이름을 지운 뒤 자동 재비교**를 할 수 있습니다."
        )
        return

    try:
        ra = compute_scores(na, ia, ta, "(선택 안 함)", debias)
        rb = compute_scores(nb, ib, tb, "(선택 안 함)", debias)
    except Exception as e:
        st.error(f"비교 분석 중 문제가 발생했습니다: {e}")
        return

    st.divider()
    st.subheader("핵심 요약 (비교)")
    m1, m2, m3 = st.columns(3)
    m1.metric("일반화 위험도 차이(시뮬)", f"{abs(ra.generalization_risk - rb.generalization_risk):.1f}")
    m2.metric("텍스트 단서 점수 차이", f"{abs(ra.content_score - rb.content_score):.1f}")
    m3.metric("형식·편향 신호 차이", f"{abs(ra.bias_score - rb.bias_score):.1f}")

    st.success(
        "두 결과 모두 **가상의 연상**입니다. 차이는 주로 **텍스트 단서**에서 오며, "
        "이름이 있을 때는 **표기 형식**에서 오는 아주 작은 시뮬레이션 신호가 더해질 수 있습니다."
    )

    st.subheader("요약 표 (시뮬레이션 수치)")
    diff_rows = [
        {
            "항목": "일반화 위험도(시뮬)",
            "A": f"{ra.generalization_risk:.1f}",
            "B": f"{rb.generalization_risk:.1f}",
            "차이(절대)": f"{abs(ra.generalization_risk - rb.generalization_risk):.1f}",
        },
        {
            "항목": "텍스트 단서 점수(상대)",
            "A": f"{ra.content_score:.1f}",
            "B": f"{rb.content_score:.1f}",
            "차이(절대)": f"{abs(ra.content_score - rb.content_score):.1f}",
        },
        {
            "항목": "형식·편향 신호(상대)",
            "A": f"{ra.bias_score:.1f}",
            "B": f"{rb.bias_score:.1f}",
            "차이(절대)": f"{abs(ra.bias_score - rb.bias_score):.1f}",
        },
    ]
    st.dataframe(diff_rows, use_container_width=True, hide_index=True)

    st.subheader("직업군 연상 비교")
    st.plotly_chart(build_fig_compare_jobs(ra, rb, "프로필 A", "프로필 B"), use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(build_fig_jobs_bar(ra, "A — 직업군 Top 3"), use_container_width=True)
        st.plotly_chart(build_fig_bias_radar(ra.bias_breakdown, "A — 편향 유형"), use_container_width=True)
    with c2:
        st.plotly_chart(build_fig_jobs_bar(rb, "B — 직업군 Top 3"), use_container_width=True)
        st.plotly_chart(build_fig_bias_radar(rb.bias_breakdown, "B — 편향 유형"), use_container_width=True)

    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(build_fig_gauge(ra.generalization_risk, "A — 일반화 위험도"), use_container_width=True)
    with g2:
        st.plotly_chart(build_fig_gauge(rb.generalization_risk, "B — 일반화 위험도"), use_container_width=True)

    st.subheader("성향 키워드 (상위 5, 비교)")
    t1, t2 = st.columns(2)
    with t1:
        st.markdown("**A**")
        for i, (k, v) in enumerate(top_n(ra.trait_scores, 5), 1):
            st.write(f"{i}. {k} — {v:.1f}")
    with t2:
        st.markdown("**B**")
        for i, (k, v) in enumerate(top_n(rb.trait_scores, 5), 1):
            st.write(f"{i}. {k} — {v:.1f}")

    st.subheader("해석 및 한계")
    with st.expander("비교 결과를 어떻게 읽을까요?", expanded=True):
        st.markdown(
            """
            - 두 프로필의 차이는 **입력 텍스트의 차이**에서 가장 크게 나옵니다.
            - 이름만 다르고 소개가 같다면, 이 데모에서는 차이가 **작게** 나오도록 이름 가중을 약하게 두었습니다.
              그럼에도 미세한 차이가 보인다면, 그것은 **표기 형식 신호의 시뮬레이션** 때문일 수 있습니다.
            - **편향 제거 모드**를 켜면 이름 표기 관련 가중이 제거되어, 비교가 더 **텍스트 중심**이 됩니다.
            """
        )

    st.subheader("왜 이 앱이 필요한가")
    with st.expander("교육·발표용 메시지", expanded=False):
        st.markdown(
            """
            자동 시스템은 사용자가 넣지 않은 속성까지 **추측으로 채우려** 할 수 있습니다.
            이 화면은 그 ‘채워 넣기’가 **얼마나 쉽게 일어날 수 있는지**를 토의용으로 보여 줍니다.
            실제 제품에서는 설명 가능성·거절권·수집 최소화 등이 함께 논의되어야 합니다.
            """
        )


def main() -> None:
    st.set_page_config(page_title="AI 편향 거울 (교육용)", layout="wide", initial_sidebar_state="expanded")
    init_session()
    inject_presentation_css()

    st.title("AI 편향 거울")
    st.markdown(
        """
        **교육·발표용 시뮬레이터**입니다. 이름·자기소개·관심사 등 **제한된 단서**만으로
        자동 추론이 어떻게 조립될 수 있는지 체험합니다.  
        **이 앱은 사람을 판정하거나 낙인을 붙이기 위한 도구가 아닙니다.**  
        입력하신 이름·문장은 **브라우저 세션 안에서만** 처리되며, 서버로 전송하거나 저장하지 않습니다(로컬 실행 기준).
        """
    )
    st.warning(
        "민감한 개인정보나 타인을 식별할 수 있는 내용은 넣지 마세요. "
        "결과는 모두 **시뮬레이션**이며, 실제 AI 모델의 출력이나 신뢰할 만한 평가가 아닙니다."
    )

    with st.sidebar:
        st.header("설정")
        mode = st.radio("모드", ["단일 분석", "비교 실험"], key="mode")
        debias = st.toggle(
            "편향 제거 모드 (이름 표기 가중 제거)",
            key="debias",
            help="켜면 텍스트 단서 위주로만 점수를 계산합니다.",
        )

        ex = st.selectbox(
            "예시 프로필 불러오기",
            ["(선택 안 함)"] + list(EXAMPLE_PROFILES.keys()),
            key="example_key",
        )
        if ex != "(선택 안 함)" and ex in EXAMPLE_PROFILES:
            prof = EXAMPLE_PROFILES[ex]
            if st.button("선택한 예시를 입력란에 적용"):
                if mode == "단일 분석":
                    st.session_state["s_name"] = prof["name"]
                    st.session_state["s_intro"] = prof["intro"]
                    st.session_state["s_interests"] = prof["interests"]
                else:
                    st.session_state["c_name_a"] = prof["name"]
                    st.session_state["c_intro_a"] = prof["intro"]
                    st.session_state["c_int_a"] = prof["interests"]
                st.rerun()

        st.divider()
        st.caption("버전: 규칙 기반 데모 · 외부 API 없음")

    if mode == "단일 분석":
        render_single(debias)
    else:
        render_compare(debias)

    st.divider()
    st.caption("© 교육용 데모 — 자동 추론의 한계와 일반화 위험을 이야기하기 위한 도구입니다.")


# if __name__ == "__main__":
#     main()
