"""
선택 기반 인생 시뮬레이터 — 상태, 노드 전이, 타임라인, 직렬화.
기획: docs/choice-based-life-simulator-dashboard-plan.md
"""

from __future__ import annotations

import copy
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 기획서 §5.2 스탯 키·범위 (시나리오 JSON과 동기화)
STAT_KEYS: tuple[str, ...] = ("health", "wealth", "happiness", "career", "relationship")
STAT_LABELS_KO: dict[str, str] = {
    "health": "건강",
    "wealth": "돈·살림",
    "happiness": "행복",
    "career": "일",
    "relationship": "사람·관계",
}

DEFAULT_SCENARIO_PATH = Path(__file__).resolve().parent / "scenarios" / "default.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_scenario(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_SCENARIO_PATH
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    validate_scenario(data)
    return data


def validate_scenario(data: dict[str, Any]) -> None:
    nodes = data.get("nodes") or {}
    if not nodes:
        raise ValueError("시나리오에 nodes가 없습니다.")
    for nid, node in nodes.items():
        for ch in node.get("choices") or []:
            nxt = ch.get("next_node_id")
            if nxt is not None and nxt not in nodes:
                raise ValueError(f"노드 {nid}: 존재하지 않는 next_node_id={nxt}")
    for req in ("scenario_id", "title", "stat_min", "stat_max", "initial_stats", "starting_age", "age_per_turn", "max_turns"):
        if req not in data:
            raise ValueError(f"시나리오 필수 필드 없음: {req}")


def clamp_stats(stats: dict[str, float], lo: float, hi: float, keys: tuple[str, ...]) -> dict[str, float]:
    out = dict(stats)
    for k in keys:
        if k in out:
            out[k] = max(lo, min(hi, float(out[k])))
    return out


def new_game(scenario: dict[str, Any], start_node_id: str = "t0") -> dict[str, Any]:
    nodes = scenario["nodes"]
    if start_node_id not in nodes:
        raise ValueError(f"시작 노드 없음: {start_node_id}")
    keys = tuple(scenario.get("stat_keys") or STAT_KEYS)
    smin = float(scenario["stat_min"])
    smax = float(scenario["stat_max"])
    init = {k: float(scenario["initial_stats"][k]) for k in keys}
    init = clamp_stats(init, smin, smax, keys)
    t0 = now_iso()
    return {
        "scenario_id": scenario["scenario_id"],
        "turn": 0,
        "age": int(scenario["starting_age"]),
        "node_id": start_node_id,
        "stats": init,
        "timeline": [
            {
                "turn": 0,
                "node_id": start_node_id,
                "choice_id": None,
                "choice_label": None,
                "stats_after": copy.deepcopy(init),
                "ts": t0,
            }
        ],
        "meta": {
            "started_at": t0,
            "ended": False,
            "ending_id": None,
        },
    }


def get_node(scenario: dict[str, Any], node_id: str) -> dict[str, Any]:
    return scenario["nodes"][node_id]


def _stat_band(v: float) -> str:
    if v < 38:
        return "low"
    if v > 62:
        return "high"
    return "mid"


_TURN_SUMMARY_CLAUSES: dict[str, dict[str, str]] = {
    "health": {
        "low": "몸이 많이 피곤하고, 쉴 틈이 거의 없어 보여요",
        "mid": "건강은 그럭저럭 버티는 정도예요",
        "high": "몸을 꽤 챙겨 와서 움직일 힘이 있어요",
    },
    "wealth": {
        "low": "통장이 빠듯해서 돈 쓸 때마다 신경이 쓰여요",
        "mid": "살림은 그냥그런 수준이에요",
        "high": "여유가 있어서 고를 수 있는 폭이 넓어요",
    },
    "happiness": {
        "low": "기분이 자주 가라앉고 만족하기 어려워요",
        "mid": "기분이 자주 오르내려요",
        "high": "지금 마음이 비교적 편하고 여유가 있어요",
    },
    "career": {
        "low": "일이나 앞길이 잘 안 보여요",
        "mid": "일은 속도를 조절하며 버티는 단계예요",
        "high": "일에서 자리와 실력이 꽤 쌓여 있어요",
    },
    "relationship": {
        "low": "사람 사이가 얇거나 어색해요",
        "mid": "사람 사이는 그때그때 달라요",
        "high": "주변 사람과 믿음이 두터운 편이에요",
    },
}


def format_turn_state_summary(
    state: dict[str, Any],
    scenario: dict[str, Any],
    protagonist_name: str,
) -> str:
    """현재 턴 시점 주인공 상태를 서술형 마크다운으로 정리."""
    name = (protagonist_name or "가상의 주인공").strip() or "가상의 주인공"
    keys = tuple(scenario.get("stat_keys") or STAT_KEYS)
    age = int(state.get("age", int(scenario["starting_age"])))
    turn = int(state.get("turn", 0))
    max_turns = int(scenario.get("max_turns", 0))
    stats = state.get("stats") or {}
    node = get_node(scenario, state["node_id"])
    scene_title = (node.get("title") or state.get("node_id") or "").strip()

    lines: list[str] = []
    lines.append(
        f"**{name}**은(는) 지금 **{age}살**이고, 지금까지 선택한 횟수는 **{turn}번**"
        + (f" (이번 판은 최대 {max_turns}번까지)" if max_turns else "")
        + "이에요."
    )
    if scene_title:
        lines.append(f"지금 장면은 「{scene_title}」이에요.")

    parts: list[str] = []
    for k in keys:
        v = float(stats.get(k, 50))
        b = _stat_band(v)
        clause = _TURN_SUMMARY_CLAUSES.get(k, {}).get(b, "")
        if clause:
            parts.append(clause)
    if parts:
        lines.append(" ".join(parts))

    timeline = state.get("timeline") or []
    if len(timeline) >= 2:
        prev = timeline[-2].get("stats_after") or {}
        cur = timeline[-1].get("stats_after") or {}
        deltas: list[str] = []
        for k in keys:
            d = float(cur.get(k, 0)) - float(prev.get(k, 0))
            if abs(d) < 1.0:
                continue
            lab = STAT_LABELS_KO.get(k, k)
            if d > 0:
                deltas.append(f"{lab} +{d:.0f}")
            else:
                deltas.append(f"{lab} {d:.0f}")
        if deltas:
            lines.append("방금 선택 직후에는 " + ", ".join(deltas) + " 쪽으로 바뀌었어요. (게임 숫자 기준이에요)")
        elif turn > 0:
            lines.append("방금 선택으로는 큰 변화는 거의 없었어요.")

    lines.append("이 글은 게임 숫자를 풀어 쓴 거예요. 진짜 건강이나 마음과 같다고 보시면 안 돼요.")
    return "\n\n".join(lines)


def apply_choice(
    state: dict[str, Any],
    scenario: dict[str, Any],
    choice_id: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if state["meta"]["ended"]:
        return None, "이미 끝난 판이에요."

    node_id = state["node_id"]
    node = get_node(scenario, node_id)
    if node.get("is_terminal"):
        return None, "이미 끝난 장면이에요. 더 고를 수 없어요."

    choice = next((c for c in (node.get("choices") or []) if c.get("id") == choice_id), None)
    if choice is None:
        return None, "그 선택은 지금 쓸 수 없어요."

    keys = tuple(scenario.get("stat_keys") or STAT_KEYS)
    smin = float(scenario["stat_min"])
    smax = float(scenario["stat_max"])
    max_turns = int(scenario["max_turns"])
    age_step = int(scenario["age_per_turn"])

    new_state = copy.deepcopy(state)
    stats = dict(new_state["stats"])
    for k, d in (choice.get("effects") or {}).items():
        if k in stats:
            stats[k] = float(stats[k]) + float(d)
    stats = clamp_stats(stats, smin, smax, keys)

    next_id = str(choice["next_node_id"])
    if stats.get("health", 1) <= 0:
        next_id = "bad_health_end"

    new_turn = int(new_state["turn"]) + 1
    new_state["turn"] = new_turn
    new_state["age"] = int(new_state["age"]) + age_step
    new_state["stats"] = stats

    nodes = scenario["nodes"]
    if next_id not in nodes:
        return None, f"다음 장면이 없어요: {next_id}"

    if new_turn >= max_turns and not nodes[next_id].get("is_terminal"):
        next_id = "time_up"

    new_state["node_id"] = next_id
    end_node = nodes[next_id]
    if end_node.get("is_terminal") or next_id in ("bad_health_end", "time_up"):
        new_state["meta"]["ended"] = True
        new_state["meta"]["ending_id"] = next_id

    new_state["timeline"].append(
        {
            "turn": new_turn,
            "node_id": node_id,
            "choice_id": choice_id,
            "choice_label": str(choice.get("label") or choice_id),
            "stats_after": copy.deepcopy(stats),
            "ts": now_iso(),
        }
    )
    return new_state, None


def state_to_json(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, indent=2)


def state_from_json(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    for k in ("scenario_id", "turn", "age", "node_id", "stats", "timeline", "meta"):
        if k not in data:
            raise ValueError(f"상태 JSON 필수 키 없음: {k}")
    return data


_STAT_FLAVOR: dict[str, str] = {
    "health": "몸 챙기는 데 마음을 많이 썼어요",
    "wealth": "돈과 살림을 튼튼히 하려고 애썼어요",
    "happiness": "지금 기분이나 만족을 자꾸 살폈어요",
    "career": "일과 앞길에 힘을 많이 넣었어요",
    "relationship": "사람과의 관계를 특히 중요하게 여겼어요",
}


def _strip_md_bold(s: str) -> str:
    return str(s).replace("**", "").replace("*", "")


def _timeline_stat_deltas(state: dict[str, Any], scenario: dict[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
    keys = tuple(scenario.get("stat_keys") or STAT_KEYS)
    timeline = state.get("timeline") or []
    net = {k: 0.0 for k in keys}
    volatility = {k: 0.0 for k in keys}
    for i in range(1, len(timeline)):
        prev = (timeline[i - 1].get("stats_after") or {}) if i > 0 else {}
        cur = timeline[i].get("stats_after") or {}
        for k in keys:
            d = float(cur.get(k, 0)) - float(prev.get(k, 0))
            net[k] += d
            volatility[k] += abs(d)
    return net, volatility


_NET_UP_PHRASE: dict[str, str] = {
    "health": "오랫동안 몸 챙기는 쪽으로 고른 선택이 많았을 거예요",
    "wealth": "돈과 살림을 튼튼히 하려는 쪽으로 자주 움직였을 거예요",
    "happiness": "기분이나 만족을 자주 살피는 삶이었을 거예요",
    "career": "일과 앞길에 힘을 많이 쏟은 때가 길었을 거예요",
    "relationship": "가족·친구·동료 손을 많이 잡으려 한 삶이었을 거예요",
}
_NET_DOWN_PHRASE: dict[str, str] = {
    "health": "몸은 자꾸 뒷전이 되거나 소홀해진 때가 많았을 거예요",
    "wealth": "통장은 늘 빠듯하게 느껴졌을 수 있어요",
    "happiness": "기분이 자주 가라앉거나 허전한 날이 많았을 수 있어요",
    "career": "일이나 앞길에서 주춤하거나 막막한 때가 잦았을 수 있어요",
    "relationship": "사람 사이가 얇아지거나 멀어지는 순간도 있었을 거예요",
}


def _biography_arc_paragraph(net: dict[str, float], keys: tuple[str, ...]) -> str:
    ranked = sorted(((k, net[k]) for k in keys), key=lambda x: -abs(x[1]))
    bits: list[str] = []
    for k, v in ranked:
        if abs(v) < 4:
            continue
        if v > 0:
            bits.append(_NET_UP_PHRASE.get(k, ""))
        else:
            bits.append(_NET_DOWN_PHRASE.get(k, ""))
    bits = [b for b in bits if b]
    if not bits:
        return "한쪽으로 크게 치우치지 않고, 그때그때 상황에 맞춰 살아간 사람 같아 보여요."
    return " ".join(bits[:3])


def _biography_volatility_sentence(top_vol_k: str, top_vol_v: float, lab: str) -> str:
    if top_vol_v < 18:
        return "크게 흔들리는 때보다는, 그냥 버티는 날이 더 많았을 수도 있어요."
    return (
        f"특히 {lab}은(는) 한번 움직이면 크게 흔들리는 패턴이 있었던 것 같아요. "
        "무엇을 먼저 챙길지 자꾸 바꿨을지도 몰라요."
    )


def _biography_final_years(stats: dict[str, Any], keys: tuple[str, ...]) -> str:
    parts: list[str] = []
    for k in keys:
        v = float(stats.get(k, 50))
        if v >= 62:
            if k == "health":
                parts.append("나이 들어서도 몸을 나름 챙긴 편으로 보여요.")
            elif k == "wealth":
                parts.append("늙어서도 살림에는 숨통이 있는 편이었을 거예요.")
            elif k == "happiness":
                parts.append("끝 무렵에는 마음이 비교적 편한 쪽에 가까웠을 거예요.")
            elif k == "career":
                parts.append("일에서는 자리나 자부심이 남아 있는 쪽으로 읽혀요.")
            else:
                parts.append("주변 사람과의 관계는 두터운 편으로 남았을 거예요.")
        elif v < 38:
            if k == "health":
                parts.append("늙어서 몸이 먼저 힘들어 보이는 면이 있어요.")
            elif k == "wealth":
                parts.append("돈 걱정은 끝까지 붙어 다녔을 수 있어요.")
            elif k == "happiness":
                parts.append("기분은 끝까지 들쭉날쭉하거나 무거웠을 수 있어요.")
            elif k == "career":
                parts.append("일에서는 힘이 빠진 느낌이 남아 있을 수 있어요.")
            else:
                parts.append("사람 사이에는 아쉬움이 남아 있을 수 있어요.")
    if not parts:
        return "마지막 무렵에는 특별히 튀는 것 없이, 평범한 선에서 살아온 사람 같아 보여요."
    return " ".join(parts[:4])


def analyze_life_narrative(state: dict[str, Any], scenario: dict[str, Any], protagonist_name: str) -> dict[str, Any]:
    """점수 나열 없이 패턴을 짐작해 일대기 형식으로 쓴다."""
    keys = tuple(scenario.get("stat_keys") or STAT_KEYS)
    name = (protagonist_name or "가상의 주인공").strip() or "가상의 주인공"
    eid = str(state.get("meta", {}).get("ending_id") or state.get("node_id"))
    end_node = scenario.get("nodes", {}).get(eid, {})
    epitaph = (end_node.get("epitaph") or "").strip()
    if not epitaph:
        epitaph = (end_node.get("body") or "한 이야기가 여기서 접혔다.").strip().split("\n")[0][:200]

    net, vol = _timeline_stat_deltas(state, scenario)
    sorted_net = sorted(((k, net[k]) for k in keys), key=lambda x: -x[1])
    sorted_vol = sorted(((k, vol[k]) for k in keys), key=lambda x: -x[1])
    top_gain_k, top_gain_v = sorted_net[0]
    top_vol_k, top_vol_v = sorted_vol[0]

    age = int(state.get("age", 0))
    epit_plain = _strip_md_bold(epitaph)
    stats = state.get("stats") or {}

    ending_heads: dict[str, str] = {
        "bad_health_end": f"{name} — 몸이 먼저 신호를 보낸 날",
        "time_up": f"{name}의 이야기, 아직 끝까지 못 쓴 책",
        "end_balanced": f"{name}, 이것저것 무너지지 않게 산 사람",
        "end_focus": f"{name}, 한 길만 파고든 사람",
        "end_warm": f"{name}, 사람을 가장 앞에 둔 사람",
    }
    headline = ending_heads.get(eid, f"{name}의 가상 이야기")

    lab_gain = STAT_LABELS_KO.get(top_gain_k, top_gain_k)
    lab_vol = STAT_LABELS_KO.get(top_vol_k, top_vol_k)
    if top_gain_v > 7:
        dek = f"길게 보면 {lab_gain} 쪽으로 마음이 많이 기울어진 삶으로 읽혀요."
    elif top_vol_v > 20:
        dek = f"{lab_vol}은(는) 자주 크게 흔들렸고, 뭐가 먼저인지도 자주 바뀌었을 거예요."
    else:
        dek = "한쪽만 쏠리지 않고, 여러 가지를 번갈아 잡으려 한 삶으로 보여요."

    if eid == "bad_health_end":
        p1 = (
            f"{name}의 이야기는 몸이 먼저 한계를 말한 채로 멈춰요. "
            f"스무 살에서 시작해 {age}살 무렵까지 걸어온 길을 한 줄로 말하면 이렇게요. {epit_plain}"
        )
    elif eid == "time_up":
        p1 = (
            f"{name}의 이야기는 정해진 턴 안에 다 쓰이지는 않았어요. "
            f"그래도 {age}살까지 찍힌 발자국을 한 줄로 묶으면 이렇게요. {epit_plain}"
        )
    else:
        p1 = (
            f"{name}은(는) {age}살 무렵, 삶의 한 장을 덮어요. "
            f"스스로 붙여 둔 책갈피에는 이런 말이 있을 법해요. {epit_plain}"
        )

    p2 = _biography_arc_paragraph(net, keys)
    p3 = _biography_volatility_sentence(top_vol_k, top_vol_v, lab_vol)
    p4 = _biography_final_years(stats, keys)
    p5 = (
        "이 글은 게임에서 고른 선택을 보고 짐작해 쓴 가상의 이야기예요. "
        "진짜 사람 한 명의 전부나 실제 삶을 대신하지 않아요."
    )

    return {
        "headline": headline,
        "dek": dek,
        "paragraphs": [p1, p2, p3, p4, p5],
        "byline": "가상 보도 · Life Sim Chronicle (배우기·실험용)",
        "name": name,
        "age": age,
    }


def format_newspaper_epilogue(
    state: dict[str, Any],
    scenario: dict[str, Any],
    protagonist_name: str,
) -> str:
    """종료 후 신문 스타일 HTML (Streamlit markdown unsafe_allow_html)."""
    story = analyze_life_narrative(state, scenario, protagonist_name)
    p_style = "line-height:1.65;margin:0 0 0.85rem 0;color:#222;text-align:justify;"
    paras_html = "".join(
        f'<p style="{p_style}">{html.escape(p)}</p>' for p in story["paragraphs"]
    )

    hl = html.escape(story["headline"])
    dk = html.escape(story["dek"])
    bl = html.escape(story["byline"])

    return f"""
<div style="font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;background:#faf8f5;border:1px solid #c9c2b8;padding:1.25rem 1.5rem;margin:0.5rem 0 1rem 0;box-shadow:0 2px 8px rgba(0,0,0,0.06);max-width:720px;">
  <div style="border-bottom:3px double #222;padding-bottom:0.5rem;margin-bottom:1rem;">
    <div style="font-size:0.75rem;letter-spacing:0.2em;color:#666;">LIFE SIM CHRONICLE · 특집</div>
    <h2 style="margin:0.35rem 0 0 0;font-size:1.55rem;line-height:1.25;color:#111;">{hl}</h2>
    <div style="margin-top:0.5rem;color:#444;font-size:0.95rem;">{dk}</div>
  </div>
  {paras_html}
  <p style="font-size:0.8rem;color:#777;border-top:1px solid #ddd;padding-top:0.75rem;margin-top:1rem;">{bl}</p>
</div>
"""


def format_life_review(state: dict[str, Any], scenario: dict[str, Any]) -> str:
    """종료 후 표시: 엔딩 epitaph + 스탯 기반 한 줄 해석."""
    if not state.get("meta", {}).get("ended"):
        return ""
    eid = state["meta"].get("ending_id") or state["node_id"]
    node = scenario.get("nodes", {}).get(eid, {})
    epitaph = (node.get("epitaph") or "").strip()
    if not epitaph:
        epitaph = (node.get("body") or "한 판의 이야기가 마무리되었다.").strip().split("\n")[0][:160]

    keys = tuple(scenario.get("stat_keys") or STAT_KEYS)
    items = sorted(((k, float(state["stats"].get(k, 0))) for k in keys), key=lambda x: -x[1])
    top_k, top_v = items[0]
    _, sec_v = items[1]
    gap = top_v - sec_v
    flavor = _STAT_FLAVOR.get(top_k, "여러 축을 오가며 선택했다")
    if gap < 8:
        tone = "다섯 가지가 비슷하게 흩어져 있어서, 한 가지만 특히 튀지는 않았어요."
    elif gap < 18:
        tone = f"그중에서도 {flavor}."
    else:
        tone = f"그중에서도 {flavor}, 다른 것보다 훨씬 눈에 띄어요."

    age = int(state.get("age", 0))
    return "\n".join(
        [
            "### 짧게 정리하면",
            epitaph,
            "",
            f"- {tone}",
            f"- 기록상 마지막은 **{age}살** 무렵이에요. 이건 게임 한 판이고, 진짜 인생과 같다고 보시면 안 돼요.",
        ]
    )


def timeline_to_csv_bytes(state: dict[str, Any], scenario: dict[str, Any]) -> bytes:
    import pandas as pd

    keys = tuple(scenario.get("stat_keys") or STAT_KEYS)
    rows = []
    for e in state["timeline"]:
        row = {
            "turn": e["turn"],
            "node_id": e.get("node_id"),
            "choice_id": e.get("choice_id"),
            "choice_label": e.get("choice_label"),
            "ts": e.get("ts"),
        }
        sa = e.get("stats_after") or {}
        for k in keys:
            row[STAT_LABELS_KO.get(k, k)] = sa.get(k)
        rows.append(row)
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode("utf-8-sig")
