"""
직책자 프로파일 대시보드 — 데이터 로딩, 집계, 요약 문장(규칙 기반).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

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
    """규칙 기반 요약(참고용). 실제 운영 시 HR 가이드와 산식을 맞출 것."""
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
