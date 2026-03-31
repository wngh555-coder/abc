"""
가상 투자 대시보드용 시세 조회 (yfinance).
기획: docs/virtual-investment-game-dashboard-plan.md — 지연 데이터 전제, 캐시는 앱에서 TTL 적용.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf


def fetch_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
    t = yf.Ticker(symbol)
    df = t.history(period=period, interval=interval, auto_adjust=True)
    if df.empty:
        return df
    df = df.rename_axis("Date").reset_index()
    if pd.api.types.is_datetime64_any_dtype(df["Date"]):
        df["Date"] = df["Date"].dt.tz_localize(None)
    return df


def fetch_latest_closes(symbols: tuple[str, ...]) -> dict[str, float]:
    """각 심볼의 가장 최근 종가. 실패/빈 데이터 심볼은 키에서 제외."""
    out: dict[str, float] = {}
    for s in symbols:
        t = yf.Ticker(s)
        h = t.history(period="10d", interval="1d", auto_adjust=True)
        if h.empty or "Close" not in h.columns:
            continue
        out[s] = float(h["Close"].iloc[-1])
    return out
