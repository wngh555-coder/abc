from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from .simulator import TeamStrength, sample_score_from_matrix, simulate_match_distribution
from .tactics import PRESETS, TeamIndices, Tactics, tactics_to_indices


@dataclass(frozen=True)
class GroupOutcome:
    expected_points: float
    rank_probs: dict[int, float]  # 1..4
    qualify_prob: float  # top2


@dataclass(frozen=True)
class TournamentOutcome:
    path_probs: dict[str, float]  # R32/R16/QF/SF/F/W


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def team_strength_from_teams_json(code: str, teams: dict) -> TeamStrength:
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


def _default_indices_for_opponent() -> TeamIndices:
    # Opponents use a neutral, "generic" tactical profile in this demo.
    return tactics_to_indices(PRESETS["Balanced"])


def simulate_group_once(
    *,
    strengths: dict[str, TeamStrength],
    group_codes: list[str],
    korea_code: str,
    korea_tactics: Tactics,
    rng: random.Random,
) -> tuple[int, dict[str, dict[str, int]]]:
    """
    Simulate a single group stage run (one realization).
    Returns:
      - korea_rank (1..4)
      - final table with keys: code -> {pts, gf, ga}
    """
    idx_kor = tactics_to_indices(korea_tactics)
    idx_opp = _default_indices_for_opponent()

    a, b, c, d = group_codes
    schedule = [(a, b), (c, d), (a, c), (b, d), (a, d), (b, c)]

    table: dict[str, dict[str, int]] = {code: {"pts": 0, "gf": 0, "ga": 0} for code in group_codes}

    for home, away in schedule:
        home_idx = idx_kor if home == korea_code else idx_opp
        away_idx = idx_kor if away == korea_code else idx_opp

        dist = simulate_match_distribution(strengths[home], strengths[away], home_idx, opp_idx=away_idx, rng=rng)
        gf, ga = sample_score_from_matrix(dist.score_matrix, rng)

        table[home]["gf"] += gf
        table[home]["ga"] += ga
        table[away]["gf"] += ga
        table[away]["ga"] += gf

        if gf > ga:
            table[home]["pts"] += 3
        elif gf == ga:
            table[home]["pts"] += 1
            table[away]["pts"] += 1
        else:
            table[away]["pts"] += 3

    # Ranking with tie-break randomization for demo purposes.
    # (Real tournaments use goal difference, goals scored, and additional criteria.)
    order = sorted(
        group_codes,
        key=lambda code: (
            table[code]["pts"],
            table[code]["gf"] - table[code]["ga"],
            table[code]["gf"],
            rng.random(),
        ),
        reverse=True,
    )
    rank = order.index(korea_code) + 1
    return rank, table


def simulate_group_monte_carlo(
    *,
    teams: dict,
    group_codes: list[str],
    korea_code: str,
    korea_tactics: Tactics,
    n: int = 1000,
    seed: int = 42,
) -> GroupOutcome:
    rng = random.Random(seed)
    strengths = {c: team_strength_from_teams_json(c, teams) for c in group_codes}
    rank_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    points_sum = 0.0

    for _ in range(n):
        rank, table = simulate_group_once(
            strengths=strengths,
            group_codes=group_codes,
            korea_code=korea_code,
            korea_tactics=korea_tactics,
            rng=rng,
        )
        rank_counts[rank] += 1
        points_sum += float(table[korea_code]["pts"])

    rank_probs = {k: v / n for k, v in rank_counts.items()}
    return GroupOutcome(
        expected_points=points_sum / n,
        rank_probs=rank_probs,
        qualify_prob=rank_probs[1] + rank_probs[2],
    )


def simulate_tournament_path_monte_carlo(
    *,
    teams: dict,
    korea_code: str,
    korea_tactics: Tactics,
    tournament_json: dict,
    group_codes: list[str],
    n: int = 1000,
    seed: int = 7,
) -> TournamentOutcome:
    rng = random.Random(seed)
    idx_kor = tactics_to_indices(korea_tactics)
    idx_opp = _default_indices_for_opponent()
    strengths = {c: team_strength_from_teams_json(c, teams) for c in teams.keys()}

    pools = tournament_json["knockout_demo"]["opponent_pools"]
    rounds = tournament_json["knockout_demo"]["rounds"]

    counts = {r: 0 for r in rounds}

    for _ in range(n):
        # 1) Group qualification (single run)
        rank, _table = simulate_group_once(
            strengths={c: strengths[c] for c in group_codes},
            group_codes=group_codes,
            korea_code=korea_code,
            korea_tactics=korea_tactics,
            rng=rng,
        )
        if rank > 2:
            continue

        counts["R32"] += 1

        # 2) Knockout matches (single elimination)
        alive = True
        for r in ["R32", "R16", "QF", "SF", "F"]:
            if not alive:
                break
            opp_code = rng.choice(pools[r])
            dist = simulate_match_distribution(
                strengths[korea_code],
                strengths[opp_code],
                idx_kor,
                opp_idx=idx_opp,
                rng=rng,
            )
            gf, ga = sample_score_from_matrix(dist.score_matrix, rng)

            # Knockout: resolve draws with a volatility-weighted coinflip.
            if gf == ga:
                # Higher volatility => more chances that either side swings the match.
                # We still keep the edge based on win_prob to stay coherent.
                p = min(0.80, max(0.20, dist.win_prob + (idx_kor.volatility - 35.0) / 220.0))
                win = rng.random() < p
            else:
                win = gf > ga

            if win:
                if r == "R32":
                    counts["R16"] += 1
                elif r == "R16":
                    counts["QF"] += 1
                elif r == "QF":
                    counts["SF"] += 1
                elif r == "SF":
                    counts["F"] += 1
                elif r == "F":
                    counts["W"] += 1
            else:
                alive = False

    path_probs = {k: (counts[k] / n) for k in counts.keys()}
    # Make it cumulative-like (each deeper implies earlier). For UI clarity, also ensure monotone.
    for r in ["R16", "QF", "SF", "F", "W"]:
        path_probs[r] = min(path_probs[r], path_probs["R32"])

    return TournamentOutcome(path_probs=path_probs)

