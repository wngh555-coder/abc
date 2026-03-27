from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Formation = Literal["4-2-3-1", "4-3-3", "3-4-3", "4-4-2"]
RiskProfile = Literal["보수", "균형", "공격"]


@dataclass(frozen=True)
class Tactics:
    formation: Formation
    pressing: int  # 0-100
    line_height: int  # 0-100
    possession: int  # 0-100
    directness: int  # 0-100
    wing_focus: int  # 0-100
    set_piece_focus: int  # 0-100
    rotation: int  # 0-100
    ace_dependency: int  # 0-100
    risk_profile: RiskProfile


@dataclass(frozen=True)
class TeamIndices:
    effective_attack: float  # 0-100-ish
    effective_defense: float
    effective_midfield: float
    effective_transition: float
    effective_stamina: float
    volatility: float  # 0-100


PRESETS: dict[str, Tactics] = {
    "Balanced": Tactics(
        formation="4-2-3-1",
        pressing=55,
        line_height=55,
        possession=55,
        directness=50,
        wing_focus=55,
        set_piece_focus=45,
        rotation=55,
        ace_dependency=50,
        risk_profile="균형",
    ),
    "High Press": Tactics(
        formation="4-3-3",
        pressing=80,
        line_height=75,
        possession=55,
        directness=55,
        wing_focus=60,
        set_piece_focus=40,
        rotation=65,
        ace_dependency=55,
        risk_profile="공격",
    ),
    "Counter Attack": Tactics(
        formation="4-4-2",
        pressing=40,
        line_height=40,
        possession=40,
        directness=80,
        wing_focus=65,
        set_piece_focus=55,
        rotation=55,
        ace_dependency=60,
        risk_profile="균형",
    ),
}


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _to01(x_0_100: int) -> float:
    return clamp01(float(x_0_100) / 100.0)


def tactics_to_indices(t: Tactics) -> TeamIndices:
    """
    Explainable, probability-friendly mapping.
    We keep everything on a ~0-100 scale so charts remain intuitive.
    Trade-offs are explicit and monotonic where possible.
    """
    p = _to01(t.pressing)
    line = _to01(t.line_height)
    poss = _to01(t.possession)
    direct = _to01(t.directness)
    wing = _to01(t.wing_focus)
    sp = _to01(t.set_piece_focus)
    rot = _to01(t.rotation)
    ace = _to01(t.ace_dependency)

    # Risk profile acts as a controlled knob: more upside + more variance.
    risk_attack_bonus = {"보수": -0.03, "균형": 0.00, "공격": 0.05}[t.risk_profile]
    risk_defense_penalty = {"보수": -0.01, "균형": 0.00, "공격": 0.04}[t.risk_profile]
    risk_vol = {"보수": -0.15, "균형": 0.00, "공격": 0.18}[t.risk_profile]

    # Formation affects "where the value comes from" rather than raw power.
    # Keep it mild: it's a style shaper in this demo, not a full engine.
    form_attack = {"4-2-3-1": 0.00, "4-3-3": 0.02, "3-4-3": 0.04, "4-4-2": 0.01}[t.formation]
    form_def = {"4-2-3-1": 0.02, "4-3-3": 0.00, "3-4-3": -0.02, "4-4-2": 0.01}[t.formation]
    form_mid = {"4-2-3-1": 0.02, "4-3-3": 0.01, "3-4-3": 0.00, "4-4-2": -0.01}[t.formation]
    form_trans = {"4-2-3-1": 0.01, "4-3-3": 0.02, "3-4-3": 0.02, "4-4-2": 0.03}[t.formation]

    # Core trade-offs (requested):
    # - Pressing ↑ → attack ↑, stamina ↓, risk ↑
    # - Line ↑ → helps pressing/territory, but increases space-behind risk (defense ↓, volatility ↑)
    # - Possession ↑ → stability ↑ (defense/midfield), but transition speed ↓
    press_attack = 0.10 * p
    press_stamina = -0.18 * p
    press_vol = 0.20 * p

    line_attack = 0.06 * line
    line_def = -0.10 * line
    line_vol = 0.12 * line

    poss_mid = 0.12 * poss
    poss_def = 0.06 * poss
    poss_trans = -0.12 * poss
    poss_vol = -0.10 * poss

    # Style knobs
    direct_attack = 0.10 * direct
    direct_mid = -0.06 * direct
    direct_trans = 0.10 * direct
    direct_vol = 0.10 * direct

    wing_attack = 0.05 * wing
    wing_mid = 0.02 * wing
    wing_vol = 0.04 * wing

    sp_attack = 0.06 * sp
    sp_vol = -0.03 * sp  # set pieces add "repeatable" chance creation (slightly stabilizing)

    # Rotation: stamina ↑, but cohesion/shot quality slightly ↓ (attack ↓, volatility ↓)
    rot_stamina = 0.14 * rot
    rot_attack = -0.04 * rot
    rot_vol = -0.06 * rot

    # Ace dependency: can lift attack ceiling but increases volatility and reduces "system defense"
    ace_attack = 0.08 * ace
    ace_def = -0.05 * ace
    ace_vol = 0.14 * ace

    # Base (neutral) index values on 0-100 scale.
    base_attack = 50.0
    base_def = 50.0
    base_mid = 50.0
    base_trans = 50.0
    base_stam = 50.0
    base_vol = 35.0

    eff_attack = base_attack + 100.0 * (
        form_attack
        + press_attack
        + line_attack
        + direct_attack
        + wing_attack
        + sp_attack
        + rot_attack
        + ace_attack
        + risk_attack_bonus
    )
    eff_def = base_def + 100.0 * (
        form_def
        + poss_def
        + line_def
        + ace_def
        - risk_defense_penalty
    )
    eff_mid = base_mid + 100.0 * (
        form_mid
        + poss_mid
        + direct_mid
        + wing_mid
    )
    eff_trans = base_trans + 100.0 * (
        form_trans
        + poss_trans
        + direct_trans
    )
    eff_stam = base_stam + 100.0 * (
        rot_stamina
        + press_stamina
    )
    vol = base_vol + 100.0 * (
        risk_vol
        + press_vol
        + line_vol
        + direct_vol
        + wing_vol
        + sp_vol
        + rot_vol
        + ace_vol
        + poss_vol
    )

    # Soft bounds for UI readability (not physics).
    def _soft_clip(x: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, x))

    return TeamIndices(
        effective_attack=_soft_clip(eff_attack, 15.0, 95.0),
        effective_defense=_soft_clip(eff_def, 15.0, 95.0),
        effective_midfield=_soft_clip(eff_mid, 15.0, 95.0),
        effective_transition=_soft_clip(eff_trans, 15.0, 95.0),
        effective_stamina=_soft_clip(eff_stam, 15.0, 95.0),
        volatility=_soft_clip(vol, 5.0, 95.0),
    )

