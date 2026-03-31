"""
가상 투자 포트폴리오 상태·매매 순수 로직.
기획: docs/virtual-investment-game-dashboard-plan.md — 정수 주, 수수료 0(MVP), 세션 상태용 dict 스키마.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

# 기획서 §5.1·§14: 단일 통화·시드 규모 (미국 주식 프리셋에 맞춤 USD)
STARTING_CASH_USD = 100_000.0
CURRENCY = "USD"
PRESET_SYMBOLS: tuple[str, ...] = ("NVDA", "AAPL", "MSFT", "SPY", "GOOGL")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def default_state() -> dict[str, Any]:
    return {
        "initial_cash": STARTING_CASH_USD,
        "cash": STARTING_CASH_USD,
        "positions": {},  # symbol -> {"qty": int, "avg_cost": float}
        "trades": [],  # {"ts","symbol","side","qty","price","fee"}
        "snapshots": [{"ts": now_iso(), "equity": STARTING_CASH_USD}],
    }


def equity(state: dict[str, Any], mark_prices: dict[str, float]) -> float:
    """현금 + 보유 평가액. 시세 없는 종목은 평균 단가로 대체."""
    total = float(state["cash"])
    for sym, pos in state["positions"].items():
        q = int(pos["qty"])
        p = mark_prices.get(sym)
        if p is None:
            p = float(pos["avg_cost"])
        total += q * p
    return total


def _append_trade(
    state: dict[str, Any],
    symbol: str,
    side: str,
    qty: int,
    price: float,
    fee: float,
) -> None:
    state["trades"].append(
        {
            "ts": now_iso(),
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "fee": fee,
        }
    )


def _append_snapshot(state: dict[str, Any], mark_prices: dict[str, float]) -> None:
    state["snapshots"].append({"ts": now_iso(), "equity": equity(state, mark_prices)})


def try_buy(
    state: dict[str, Any],
    symbol: str,
    qty: int,
    price: float,
    mark_prices: dict[str, float],
    fee: float = 0.0,
) -> tuple[dict[str, Any] | None, str | None]:
    if qty < 1:
        return None, "수량은 1주 이상의 정수여야 합니다."
    cost = qty * price + fee
    if state["cash"] < cost - 1e-9:
        return None, "가용 현금이 부족합니다."

    new_state = copy.deepcopy(state)
    pos = new_state["positions"].get(symbol, {"qty": 0, "avg_cost": 0.0})
    old_q = int(pos["qty"])
    old_c = float(pos["avg_cost"])
    new_q = old_q + qty
    new_avg = (old_q * old_c + qty * price) / new_q if new_q else price
    new_state["positions"][symbol] = {"qty": new_q, "avg_cost": new_avg}
    new_state["cash"] = float(new_state["cash"]) - cost
    _append_trade(new_state, symbol, "BUY", qty, price, fee)

    marks = dict(mark_prices)
    marks[symbol] = price
    for s, p in new_state["positions"].items():
        marks.setdefault(s, float(p["avg_cost"]))
    _append_snapshot(new_state, marks)
    return new_state, None


def try_sell(
    state: dict[str, Any],
    symbol: str,
    qty: int,
    price: float,
    mark_prices: dict[str, float],
    fee: float = 0.0,
) -> tuple[dict[str, Any] | None, str | None]:
    if qty < 1:
        return None, "수량은 1주 이상의 정수여야 합니다."
    pos = state["positions"].get(symbol)
    if not pos or int(pos["qty"]) < qty:
        return None, "보유 수량이 부족합니다."

    new_state = copy.deepcopy(state)
    proceeds = qty * price - fee
    new_state["cash"] = float(new_state["cash"]) + proceeds
    rem = int(new_state["positions"][symbol]["qty"]) - qty
    if rem == 0:
        del new_state["positions"][symbol]
    else:
        new_state["positions"][symbol]["qty"] = rem
    _append_trade(new_state, symbol, "SELL", qty, price, fee)

    marks = dict(mark_prices)
    marks[symbol] = price
    for s, p in new_state["positions"].items():
        marks.setdefault(s, float(p["avg_cost"]))
    _append_snapshot(new_state, marks)
    return new_state, None


def state_to_json(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, indent=2)


def state_from_json(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    required = ("initial_cash", "cash", "positions", "trades", "snapshots")
    for k in required:
        if k not in data:
            raise ValueError(f"필수 키 없음: {k}")
    return data


def trades_to_csv_bytes(state: dict[str, Any]) -> bytes:
    import pandas as pd

    if not state["trades"]:
        return "ts,symbol,side,qty,price,fee\n".encode("utf-8-sig")
    df = pd.DataFrame(state["trades"])
    return df.to_csv(index=False).encode("utf-8-sig")


def snapshots_to_csv_bytes(state: dict[str, Any]) -> bytes:
    import pandas as pd

    if not state["snapshots"]:
        return "ts,equity\n".encode("utf-8-sig")
    df = pd.DataFrame(state["snapshots"])
    return df.to_csv(index=False).encode("utf-8-sig")
