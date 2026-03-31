"""
세계 트렌드 데모용 데이터 생성 (시드 기반 시뮬레이션).
운영 시 동일 스키마로 뉴스/RSS·소셜 집계 결과를 주입하면 된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TrendSnapshot:
    """대시보드에 넘기는 단일 스냅샷."""

    word_freq: dict[str, float]
    country_df: pd.DataFrame
    timeline_df: pd.DataFrame
    label_topic: str
    generated_at: datetime


# 주제별 키워드 풀 (뉴스/트위터 스타일 혼합)
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "테크·AI": [
        "AI",
        "GPU",
        "반도체",
        "클라우드",
        "규제",
        "스타트업",
        "LLM",
        "데이터센터",
        "투자",
        "빅테크",
        "오픈소스",
        "보안",
        "칩",
        "생성형",
        "자율주행",
    ],
    "기후·에너지": [
        "기후",
        "탄소",
        "재생에너지",
        "배출",
        "COP",
        "전기차",
        "배터리",
        "태양광",
        "석유",
        "가뭄",
        "폭염",
        "환경",
        "ESG",
        "수소",
        "그린",
    ],
    "지정학·안보": [
        "외교",
        "제재",
        "동맹",
        "군사",
        "협상",
        "선거",
        "난민",
        "무역",
        "관세",
        "해협",
        "NATO",
        "중동",
        "아시아",
        "유럽",
        "안보",
    ],
}

# Choropleth용 ISO-3166 alpha-3
COUNTRY_ISO3: list[str] = [
    "USA",
    "GBR",
    "DEU",
    "FRA",
    "JPN",
    "KOR",
    "CHN",
    "IND",
    "BRA",
    "CAN",
    "AUS",
    "ITA",
    "ESP",
    "MEX",
    "NLD",
    "SWE",
    "CHE",
    "SAU",
    "ARE",
    "SGP",
]

COUNTRY_NAMES_KO: dict[str, str] = {
    "USA": "미국",
    "GBR": "영국",
    "DEU": "독일",
    "FRA": "프랑스",
    "JPN": "일본",
    "KOR": "한국",
    "CHN": "중국",
    "IND": "인도",
    "BRA": "브라질",
    "CAN": "캐나다",
    "AUS": "호주",
    "ITA": "이탈리아",
    "ESP": "스페인",
    "MEX": "멕시코",
    "NLD": "네덜란드",
    "SWE": "스웨덴",
    "CHE": "스위스",
    "SAU": "사우디",
    "ARE": "UAE",
    "SGP": "싱가포르",
}


def list_topic_ids() -> list[str]:
    return list(TOPIC_KEYWORDS.keys())


def simulate_trends(
    seed: int,
    topic_id: str,
    hours: int = 48,
) -> TrendSnapshot:
    """
    시드·주제·기간에 따라 워드 가중치, 국가 관심도, 시계열 트렌드를 생성한다.
    """
    if topic_id not in TOPIC_KEYWORDS:
        topic_id = list(TOPIC_KEYWORDS.keys())[0]

    rng = np.random.default_rng(seed)
    base = np.array(TOPIC_KEYWORDS[topic_id], dtype=object)
    # 노이즈 키워드(트위터/뉴스 잡음)
    noise = [
        "Breaking",
        "실시간",
        "화제",
        "급등",
        "이슈",
        "속보",
        "반응",
        "댓글",
        "트렌드",
        "검색",
    ]
    words = np.concatenate([base, np.array(noise, dtype=object)])
    weights = rng.uniform(0.3, 1.0, size=len(words))
    # 일부 키워드만 강조
    hot_idx = rng.choice(len(words), size=min(5, len(words)), replace=False)
    weights[hot_idx] *= rng.uniform(2.0, 4.0, size=len(hot_idx))
    word_freq = {str(w): float(weights[i]) for i, w in enumerate(words)}

    # 국가별 관심도: 주제에 따라 특정 지역 가중
    topic_bias = {"테크·AI": "USA", "기후·에너지": "DEU", "지정학·안보": "USA"}
    bias_iso = topic_bias.get(topic_id, "USA")
    interest = rng.uniform(15.0, 55.0, size=len(COUNTRY_ISO3))
    if bias_iso in COUNTRY_ISO3:
        interest[COUNTRY_ISO3.index(bias_iso)] += rng.uniform(25.0, 45.0)
    interest = np.clip(interest, 5.0, 100.0)
    country_df = pd.DataFrame(
        {
            "iso_alpha3": COUNTRY_ISO3,
            "interest": interest,
            "country_ko": [COUNTRY_NAMES_KO[c] for c in COUNTRY_ISO3],
        }
    )

    # 시간별 트렌드 (합성 점수)
    utc_now = datetime.now(timezone.utc)
    start = utc_now - timedelta(hours=hours)
    step = max(1, hours // min(hours, 48))
    times = []
    scores = []
    t = start
    wave = rng.uniform(0.8, 1.2)
    i = 0
    while t <= utc_now:
        seasonal = 50.0 + 35.0 * np.sin(i / 4.0 + seed * 0.01)
        spike = 15.0 if (i % max(1, hours // 8) == 0) else 0.0
        noise_v = rng.normal(0, 6.0)
        scores.append(float(np.clip(seasonal * wave + spike + noise_v, 5.0, 100.0)))
        times.append(t)
        t += timedelta(hours=step)
        i += 1

    timeline_df = pd.DataFrame(
        {
            "time_utc": times,
            "trend_score": scores,
        }
    )

    return TrendSnapshot(
        word_freq=word_freq,
        country_df=country_df,
        timeline_df=timeline_df,
        label_topic=topic_id,
        generated_at=utc_now,
    )
