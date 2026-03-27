"""
사내 인사 통계 대시보드: 로딩·전처리·필터·KPI (Streamlit 위젯과 분리)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

COL_LABELS = {
    "employee_id": "직원코드",
    "snapshot_date": "스냅샷일",
    "division": "본부",
    "dept": "부서",
    "team": "팀",
    "location": "지역",
    "job_family": "직군",
    "grade": "직급",
    "employment_type": "고용형태",
    "status": "재직상태",
    "hire_date": "입사일",
    "termination_date": "퇴사일",
    "tenure_months": "근속(월)",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def load_hr_employees() -> pd.DataFrame:
    csv_path = _repo_root() / "data" / "sample_hr_employees.csv"
    if csv_path.is_file():
        return pd.read_csv(csv_path)
    return _synthetic_employees()


def _synthetic_employees() -> pd.DataFrame:
    rng = pd.date_range("2020-01-15", periods=48, freq="ME")
    rows = []
    divisions = ["DX본부", "제조본부", "경영지원본부"]
    for i in range(80):
        div = divisions[i % 3]
        hire = rng[i % len(rng)] - pd.DateOffset(months=(i % 36) + 1)
        status = "재직" if i % 10 != 0 else ("휴직" if i % 20 == 0 else "퇴사")
        term = pd.NaT
        if status == "퇴사":
            term = hire + pd.DateOffset(months=6 + (i % 18))
        rows.append(
            {
                "employee_id": f"EMP{i+1:04d}",
                "snapshot_date": "2025-03-01",
                "division": div,
                "dept": f"{div[:2]}운영{i % 4 + 1}팀",
                "team": f"셀{(i % 3) + 1}",
                "location": ["서울", "판교", "부산", "대전"][i % 4],
                "job_family": ["개발", "영업", "기획", "운영"][i % 4],
                "grade": ["사원", "대리", "과장", "차장", "부장"][i % 5],
                "employment_type": ["정규직", "계약직", "인턴"][i % 7 % 3],
                "status": status,
                "hire_date": hire.strftime("%Y-%m-%d"),
                "termination_date": "" if pd.isna(term) else term.strftime("%Y-%m-%d"),
            }
        )
    return pd.DataFrame(rows)


def prepare_hr_employees(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["snapshot_date"] = pd.to_datetime(out["snapshot_date"], errors="coerce")
    out["hire_date"] = pd.to_datetime(out["hire_date"], errors="coerce")
    out["termination_date"] = pd.to_datetime(out["termination_date"], errors="coerce")
    snap = out["snapshot_date"].iloc[0] if len(out) else pd.Timestamp.today()
    if pd.isna(snap):
        snap = pd.Timestamp.today()
    delta = (snap.normalize() - out["hire_date"].dt.normalize()).dt.days
    out["tenure_months"] = (delta / 30.4375).round(1)
    out["hire_month"] = out["hire_date"].dt.to_period("M").dt.to_timestamp()
    return out


def filter_hr_employees(
    df: pd.DataFrame,
    *,
    divisions: list[str],
    depts: list[str],
    locations: list[str],
    job_families: list[str],
    grades: list[str],
    employment_types: list[str],
    statuses: list[str],
    tenure_range: tuple[float, float],
) -> pd.DataFrame:
    t_lo, t_hi = tenure_range
    m = (
        df["division"].isin(divisions)
        & df["dept"].isin(depts)
        & df["location"].isin(locations)
        & df["job_family"].isin(job_families)
        & df["grade"].isin(grades)
        & df["employment_type"].isin(employment_types)
        & df["status"].isin(statuses)
        & df["tenure_months"].between(t_lo, t_hi)
    )
    return df.loc[m].copy()


def kpi_from_filtered(filtered: pd.DataFrame) -> dict:
    n = len(filtered)
    active = int((filtered["status"] == "재직").sum()) if n else 0
    reg = int((filtered["employment_type"] == "정규직").sum()) if n else 0
    reg_rate = (reg / n * 100) if n else 0.0
    mean_tenure = float(filtered["tenure_months"].mean()) if n else None
    hired_12m = 0
    if n:
        snap = filtered["snapshot_date"].iloc[0]
        if not pd.isna(snap):
            cutoff = snap - pd.DateOffset(months=12)
            hired_12m = int(filtered["hire_date"].ge(cutoff).sum())
    return {
        "n_total": n,
        "n_active": active,
        "n_regular": reg,
        "regular_rate": reg_rate,
        "mean_tenure": mean_tenure,
        "hired_12m": hired_12m,
    }
