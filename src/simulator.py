from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .tactics import TeamIndices


@dataclass(frozen=True)
class TeamStrength:
    code: str
    name: str
    attack: float
    defense: float
    midfield: float
    transition: float
    stamina: float


@dataclass(frozen=True)
class MatchResultDistribution:
    exp_goals_for: float
    exp_goals_against: float
    win_prob: float
    draw_prob: float
    loss_prob: float
    most_likely_score: tuple[int, int]
    score_matrix: list[list[float]]  # [gf][ga] for 0..max_goals


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def poisson_pmf(k: int, lam: float) -> float:
    lam = max(1e-6, lam)
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def truncated_poisson_probs(lam: float, max_goals: int = 5) -> list[float]:
    probs = [poisson_pmf(k, lam) for k in range(max_goals + 1)]
    s = sum(probs)
    if s <= 0:
        return [1.0] + [0.0] * max_goals
    return [p / s for p in probs]


def expected_goals(
    team: TeamStrength,
    opp: TeamStrength,
    idx: TeamIndices,
    opp_idx: TeamIndices | None = None,
    home_adv: float = 0.03,
) -> float:
    """
    Small, explainable xG generator.
    - Base from team attack vs opponent defense (ratings on 0..100-ish)
    - Tactical indices tilt the match-up
    - Volatility increases spread by nudging expected goals away from the mean
    """
    opp_idx = opp_idx or TeamIndices(
        effective_attack=50, effective_defense=50, effective_midfield=50, effective_transition=50, effective_stamina=50, volatility=35
    )

    # Normalize to roughly -1..+1
    rating_edge = (team.attack - opp.defense) / 25.0
    mid_edge = (team.midfield - opp.midfield) / 40.0

    # Tactical edges (0..100 -> centered)
    atk_edge = (idx.effective_attack - 50.0) / 35.0
    trans_edge = (idx.effective_transition - 50.0) / 40.0
    poss_control = (idx.effective_midfield - 50.0) / 50.0

    # Defense of opponent also matters: high defensive index reduces our xG slightly.
    opp_def = (opp_idx.effective_defense - 50.0) / 45.0

    # Stamina affects late-game chance quality (very mild).
    stamina = (idx.effective_stamina - 50.0) / 80.0

    # A stable baseline xG for international matches.
    base = 1.15
    xg = base + 0.55 * rating_edge + 0.20 * mid_edge + 0.25 * atk_edge + 0.18 * trans_edge + 0.12 * poss_control - 0.18 * opp_def
    xg *= (1.0 + home_adv)
    xg *= (1.0 + 0.06 * stamina)

    # Keep within plausible range for demo (0.2 ~ 3.2)
    return max(0.20, min(3.20, xg))


def simulate_match_distribution(
    team: TeamStrength,
    opp: TeamStrength,
    idx: TeamIndices,
    opp_idx: TeamIndices | None = None,
    max_goals: int = 5,
    rng: random.Random | None = None,
) -> MatchResultDistribution:
    rng = rng or random.Random()

    lam_for = expected_goals(team, opp, idx, opp_idx=opp_idx)
    lam_against = expected_goals(opp, team, opp_idx or TeamIndices(50, 50, 50, 50, 50, 35), opp_idx=idx, home_adv=0.0)

    # Volatility increases uncertainty by shifting xG slightly toward extremes.
    vol = max(0.0, min(1.0, (idx.volatility - 35.0) / 70.0))
    lam_for = lam_for * (1.0 + 0.10 * vol)
    lam_against = lam_against * (1.0 + 0.10 * vol)

    pf = truncated_poisson_probs(lam_for, max_goals=max_goals)
    pa = truncated_poisson_probs(lam_against, max_goals=max_goals)

    mat: list[list[float]] = [[0.0 for _ in range(max_goals + 1)] for __ in range(max_goals + 1)]
    win = draw = loss = 0.0
    best_p = -1.0
    best_score = (0, 0)

    for gf in range(max_goals + 1):
        for ga in range(max_goals + 1):
            p = pf[gf] * pa[ga]
            mat[gf][ga] = p
            if gf > ga:
                win += p
            elif gf == ga:
                draw += p
            else:
                loss += p
            if p > best_p:
                best_p = p
                best_score = (gf, ga)

    # Expected goals from truncated distribution (good enough for the 0..5 model).
    exp_for = sum(g * pf[g] for g in range(max_goals + 1))
    exp_against = sum(g * pa[g] for g in range(max_goals + 1))

    # Tiny calibration: strong defense index slightly increases draw probability in tight matches.
    tightness = _sigmoid(-(lam_for - lam_against) * 1.2)
    draw_boost = max(0.0, min(0.06, (idx.effective_defense - 50.0) / 900.0))
    draw = min(1.0, draw + draw_boost * tightness)
    rem = max(0.0, 1.0 - draw)
    wl = max(1e-9, win + loss)
    win = rem * (win / wl)
    loss = rem * (loss / wl)

    return MatchResultDistribution(
        exp_goals_for=exp_for,
        exp_goals_against=exp_against,
        win_prob=win,
        draw_prob=draw,
        loss_prob=loss,
        most_likely_score=best_score,
        score_matrix=mat,
    )


def sample_score_from_matrix(mat: list[list[float]], rng: random.Random) -> tuple[int, int]:
    flat: list[tuple[int, int, float]] = []
    for gf in range(len(mat)):
        for ga in range(len(mat[0])):
            flat.append((gf, ga, mat[gf][ga]))
    total = sum(p for _, _, p in flat)
    if total <= 0:
        return (0, 0)
    r = rng.random() * total
    acc = 0.0
    for gf, ga, p in flat:
        acc += p
        if acc >= r:
            return (gf, ga)
    return (flat[-1][0], flat[-1][1])

