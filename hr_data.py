"""
HR 적임자 선발 대시보드 — 데이터 로딩·규칙 평가 (순수 함수).
기획: docs/hr-candidate-fit-dashboard-plan.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
DEFAULT_TRACKS_PATH = ROOT / "config" / "tracks.json"
DEFAULT_CANDIDATES_PATH = ROOT / "data" / "sample_hr_candidates.csv"


def load_tracks(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_TRACKS_PATH
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def load_candidates(path: Path | str | None = None) -> pd.DataFrame:
    p = Path(path) if path else DEFAULT_CANDIDATES_PATH
    df = pd.read_csv(p)
    for col in df.columns:
        if col in ("family_can_relocate", "disciplinary_issue", "return_obligation_ok"):
            df[col] = df[col].astype(str).str.strip().str.upper()
    return df


def _get_field_value(row: pd.Series, field: str) -> Any:
    if field not in row.index:
        return None
    v = row[field]
    if pd.isna(v):
        return None
    if field in (
        "tenure_months",
        "english_toeic",
        "months_abroad_total",
        "travel_readiness_1_5",
    ):
        try:
            fv = float(v)
            return int(fv) if fv.is_integer() else fv
        except (TypeError, ValueError):
            return v
    return v


def _cmp_numeric(left: float | int, op: str, right: float | int) -> bool:
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == "==":
        return left == right
    raise ValueError(f"지원하지 않는 연산자: {op}")


def _cmp_str(left: str, op: str, right: str) -> bool:
    ls = str(left).strip().upper()
    rs = str(right).strip().upper()
    if op == "==":
        return ls == rs
    raise ValueError(f"문자열은 == 만 지원: {op}")


def evaluate_row_for_track(row: pd.Series, track: dict[str, Any]) -> dict[str, Any]:
    """단일 후보에 대해 필수·제외·우대 규칙을 평가한다."""
    required_ok: list[tuple[str, bool, str]] = []
    exclude_hit = False
    exclude_reasons: list[str] = []
    preferred_score = 0.0
    preferred_max = 0.0
    preferred_detail: list[dict[str, Any]] = []

    for req in track.get("requirements") or []:
        kind = req.get("kind")
        field = req["field"]
        op = req["op"]
        label = req.get("label") or req.get("id")
        val = _get_field_value(row, field)

        if kind == "exclude":
            target = req.get("value_str")
            if target is not None:
                ok_exclude = _cmp_str(val if val is not None else "", op, target)
            else:
                ok_exclude = False
            if ok_exclude:
                exclude_hit = True
                exclude_reasons.append(label)
            continue

        if kind == "required":
            pass_req = False
            if "value_str" in req:
                pass_req = _cmp_str(val if val is not None else "", op, req["value_str"])
            else:
                num_v = float(val) if val is not None else float("nan")
                pass_req = not pd.isna(num_v) and _cmp_numeric(num_v, op, float(req["value"]))
            required_ok.append((req.get("id", label), pass_req, label))

    for pref in track.get("preferred") or []:
        w = float(pref.get("weight") or 0)
        preferred_max += w
        field = pref["field"]
        op = pref["op"]
        val = _get_field_value(row, field)
        ok = False
        if "value_str" in pref:
            ok = _cmp_str(val if val is not None else "", op, pref["value_str"])
        else:
            num_v = float(val) if val is not None else float("nan")
            ok = not pd.isna(num_v) and _cmp_numeric(num_v, op, float(pref["value"]))
        if ok:
            preferred_score += w
        preferred_detail.append(
            {
                "id": pref.get("id"),
                "label": pref.get("label"),
                "met": ok,
                "weight": w,
            }
        )

    required_pass = all(p for _, p, _ in required_ok) and not exclude_hit
    norm_score = (preferred_score / preferred_max * 100) if preferred_max > 0 else 0.0

    return {
        "meets_required": required_pass,
        "exclude_hit": exclude_hit,
        "exclude_reasons": exclude_reasons,
        "required_detail": [{"id": i, "pass": p, "label": lbl} for i, p, lbl in required_ok],
        "preferred_score": preferred_score,
        "preferred_max": preferred_max,
        "preferred_norm_0_100": round(norm_score, 1),
        "preferred_detail": preferred_detail,
    }


def add_track_evaluation(df: pd.DataFrame, track: dict[str, Any], weight_multiplier: float = 1.0) -> pd.DataFrame:
    out = df.copy()
    rows = []
    for _, row in out.iterrows():
        ev = evaluate_row_for_track(row, track)
        rows.append(
            {
                "meets_required": ev["meets_required"],
                "exclude_hit": ev["exclude_hit"],
                "fit_score_0_100": round(
                    ev["preferred_norm_0_100"] * weight_multiplier
                    if ev["meets_required"]
                    else 0.0,
                    1,
                ),
                "preferred_raw": ev["preferred_score"],
                "preferred_max": ev["preferred_max"],
            }
        )
    ev_df = pd.DataFrame(rows, index=out.index)
    return pd.concat([out, ev_df], axis=1)


def filter_candidates(
    df: pd.DataFrame,
    *,
    dept: str | None,
    job_family: str | None,
    tenure_min: int,
    tenure_max: int,
    english_min_extra: int,
    months_abroad_min: int,
    family_relocate_only: bool,
) -> pd.DataFrame:
    m = pd.Series(True, index=df.index)
    if dept and dept != "(전체)":
        m &= df["dept"] == dept
    if job_family and job_family != "(전체)":
        m &= df["job_family"] == job_family
    m &= df["tenure_months"].between(tenure_min, tenure_max)
    m &= df["english_toeic"] >= english_min_extra
    m &= df["months_abroad_total"] >= months_abroad_min
    if family_relocate_only:
        m &= df["family_can_relocate"] == "Y"
    return df.loc[m].copy()


def track_by_id(tracks_cfg: dict[str, Any], track_id: str) -> dict[str, Any]:
    for t in tracks_cfg.get("tracks") or []:
        if t.get("id") == track_id:
            return t
    raise KeyError(track_id)


def aggregate_requirement_pass_rates(df: pd.DataFrame, track: dict[str, Any]) -> pd.DataFrame:
    """필터된 집단에서 요건별 충족 인원 비율."""
    reqs = [r for r in (track.get("requirements") or []) if r.get("kind") == "required"]
    if not reqs or df.empty:
        return pd.DataFrame(columns=["요건", "충족_수", "대상_수", "충족률_%"])
    total = len(df)
    counts = {r.get("id"): 0 for r in reqs if r.get("id")}
    for _, row in df.iterrows():
        ev = evaluate_row_for_track(row, track)
        by_id = {d["id"]: d["pass"] for d in ev["required_detail"]}
        for rid in counts:
            if by_id.get(rid):
                counts[rid] += 1
    rows_out = []
    for r in reqs:
        rid = r.get("id")
        ok = counts.get(rid, 0) if rid else 0
        rows_out.append(
            {
                "요건": r.get("label"),
                "충족_수": ok,
                "대상_수": total,
                "충족률_%": round(100.0 * ok / total, 1),
            }
        )
    return pd.DataFrame(rows_out)


def radar_metrics(row: pd.Series) -> dict[str, float]:
    """차트용 0~100 정규화 (규칙 기반, 설명 가능)."""
    toeic = float(row.get("english_toeic") or 0)
    tenure = float(row.get("tenure_months") or 0)
    abroad = float(row.get("months_abroad_total") or 0)
    readi = float(row.get("travel_readiness_1_5") or 0)
    return {
        "영어(정규화)": max(0.0, min(100.0, (toeic - 400) / (990 - 400) * 100)),
        "근속(정규화)": max(0.0, min(100.0, tenure / 120 * 100)),
        "해외경험(정규화)": max(0.0, min(100.0, abroad / 36 * 100)),
        "출장적합(자가)": max(0.0, min(100.0, readi / 5 * 100)),
    }
