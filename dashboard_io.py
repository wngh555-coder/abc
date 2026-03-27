"""
대시보드용 데이터 로딩·전처리·필터 (Streamlit 위젯과 분리된 순수 로직)
"""

from pathlib import Path

import pandas as pd

COL_LABELS = {
    "survived": "생존",
    "pclass": "객실 등급",
    "sex": "성별",
    "age": "나이",
    "sibsp": "형제·배우자",
    "parch": "부모·자녀",
    "fare": "운임",
    "embarked": "승선 항구",
    "class": "객실 등급(범주)",
    "who": "구분(남/여/아이)",
    "adult_male": "성인 남성",
    "deck": "갑판",
    "embark_town": "승선 도시",
    "alive": "생존 여부",
    "alone": "단독 승선",
}


def load_titanic() -> pd.DataFrame:
    csv_path = Path(__file__).resolve().parent / "titanic.csv"
    if csv_path.is_file():
        return pd.read_csv(csv_path)
    import seaborn as sns

    return sns.load_dataset("titanic")


def prepare_titanic(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["embarked"] = out["embarked"].fillna("미상")
    return out


def filter_titanic(
    df: pd.DataFrame,
    *,
    sex_opt: list,
    class_opt: list,
    embarked_opt: list,
    age_range: tuple[float, float],
) -> pd.DataFrame:
    lo, hi = age_range
    mask = (
        df["sex"].isin(sex_opt)
        & df["pclass"].isin(class_opt)
        & df["embarked"].isin(embarked_opt)
        & df["age"].between(lo, hi)
    )
    return df.loc[mask].copy()


def kpi_from_filtered(filtered: pd.DataFrame) -> dict:
    n_total = len(filtered)
    n_surv = int(filtered["survived"].sum()) if n_total else 0
    rate = (n_surv / n_total * 100) if n_total else 0.0
    mean_fare = float(filtered["fare"].mean()) if n_total else None
    return {
        "n_total": n_total,
        "n_surv": n_surv,
        "rate": rate,
        "mean_fare": mean_fare,
    }
