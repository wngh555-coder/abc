"""
가상 투자 게임 대시보드 (Streamlit)
기획: docs/virtual-investment-game-dashboard-plan.md

실행: streamlit run virtual_invest_app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from virtual_invest_charts import fig_allocation, fig_equity_curve, fig_price_line
from virtual_invest_quotes import fetch_history, fetch_latest_closes
from virtual_invest_state import (
    CURRENCY,
    PRESET_SYMBOLS,
    STARTING_CASH_USD,
    default_state,
    equity,
    snapshots_to_csv_bytes,
    state_from_json,
    state_to_json,
    trades_to_csv_bytes,
    try_buy,
    try_sell,
)

st.set_page_config(
    page_title="가상 투자 게임",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

SESSION_KEY = "vi_state"


@st.cache_data(ttl=300)
def cached_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
    return fetch_history(symbol, period, interval)


@st.cache_data(ttl=300)
def cached_latest_closes(symbols: tuple[str, ...]) -> dict[str, float]:
    return fetch_latest_closes(symbols)


def _symbols_for_marks(state: dict) -> tuple[str, ...]:
    held = tuple(sorted(state["positions"].keys()))
    return tuple(sorted(set(PRESET_SYMBOLS) | set(held)))


if SESSION_KEY not in st.session_state:
    st.session_state[SESSION_KEY] = default_state()

st.title("🎮 가상 투자 게임 대시보드")
st.caption(
    f"기준 통화: **{CURRENCY}** · 시드: **${STARTING_CASH_USD:,.0f}** · 시세는 yfinance 지연 데이터이며 교육용 시뮬레이션입니다."
)

state = st.session_state[SESSION_KEY]
marks = cached_latest_closes(_symbols_for_marks(state))
eq = equity(state, marks)
initial = float(state["initial_cash"])
pnl = eq - initial
pnl_pct = (pnl / initial * 100) if initial else 0.0
n_pos = len(state["positions"])

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("가용 현금", f"${state['cash']:,.2f}")
c2.metric("총 자산", f"${eq:,.2f}")
c3.metric("누적 손익", f"${pnl:+,.2f}")
c4.metric("수익률", f"{pnl_pct:+.2f}%")
c5.metric("보유 종목 수", f"{n_pos}")

st.divider()

with st.sidebar:
    st.header("거래 & 설정")
    symbol = st.selectbox("종목 (프리셋)", options=list(PRESET_SYMBOLS), index=0)
    period = st.selectbox(
        "시세 차트 기간",
        options=["1mo", "3mo", "6mo", "1y", "ytd", "max"],
        index=2,
    )
    interval = st.selectbox("시세 간격", options=["1d", "1wk"], index=0)
    qty = st.number_input("주문 수량 (정수 주)", min_value=1, value=1, step=1)

    last_px = marks.get(symbol)
    if last_px is not None:
        st.caption(f"{symbol} 기준가(최근 종가): **${last_px:,.2f}**")
    else:
        st.warning(f"{symbol} 시세를 가져오지 못했습니다. 네트워크·심볼을 확인하세요.")

    if st.button("매수", type="primary", use_container_width=True):
        if last_px is None:
            st.error("시세가 없어 매수할 수 없습니다.")
        else:
            new_state, err = try_buy(state, symbol, int(qty), last_px, marks, fee=0.0)
            if err:
                st.warning(err)
            else:
                st.session_state[SESSION_KEY] = new_state
                st.success(f"{symbol} {qty}주 매수 체결 (${last_px:,.2f})")
                st.rerun()

    if st.button("매도", use_container_width=True):
        if last_px is None:
            st.error("시세가 없어 매도할 수 없습니다.")
        else:
            new_state, err = try_sell(state, symbol, int(qty), last_px, marks, fee=0.0)
            if err:
                st.warning(err)
            else:
                st.session_state[SESSION_KEY] = new_state
                st.success(f"{symbol} {qty}주 매도 체결 (${last_px:,.2f})")
                st.rerun()

    st.divider()
    if st.button("게임 초기화 (시드 머니로 리셋)", use_container_width=True):
        st.session_state[SESSION_KEY] = default_state()
        st.rerun()

    st.subheader("저장 / 불러오기")
    st.download_button(
        "상태 JSON 내려받기",
        data=state_to_json(st.session_state[SESSION_KEY]).encode("utf-8"),
        file_name="virtual_invest_state.json",
        mime="application/json",
        use_container_width=True,
    )
    st.download_button(
        "거래 내역 CSV",
        data=trades_to_csv_bytes(st.session_state[SESSION_KEY]),
        file_name="virtual_invest_trades.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.download_button(
        "자산 스냅샷 CSV",
        data=snapshots_to_csv_bytes(st.session_state[SESSION_KEY]),
        file_name="virtual_invest_equity_snapshots.csv",
        mime="text/csv",
        use_container_width=True,
    )
    up = st.file_uploader("상태 JSON 불러오기", type=["json"])
    if up is not None:
        if st.button("JSON 적용", use_container_width=True):
            try:
                raw = up.read().decode("utf-8")
                st.session_state[SESSION_KEY] = state_from_json(raw)
                st.success("상태를 불러왔습니다.")
                st.rerun()
            except Exception as e:
                st.error(f"불러오기 실패: {e}")

tab_eq, tab_px, tab_alloc = st.tabs(["자산 곡선", "시세 차트", "자산 배분"])

hist = cached_history(symbol, period, interval)

with tab_eq:
    st.plotly_chart(fig_equity_curve(state["snapshots"]), use_container_width=True)

with tab_px:
    st.plotly_chart(fig_price_line(hist, symbol), use_container_width=True)

with tab_alloc:
    pos_vals = {}
    for sym, pos in state["positions"].items():
        px_ = marks.get(sym, float(pos["avg_cost"]))
        pos_vals[sym] = int(pos["qty"]) * float(px_)
    st.plotly_chart(fig_allocation(float(state["cash"]), pos_vals), use_container_width=True)

left, right = st.columns(2)
with left:
    st.subheader("보유 종목")
    rows = []
    for sym, pos in sorted(state["positions"].items()):
        q = int(pos["qty"])
        ac = float(pos["avg_cost"])
        mp = marks.get(sym, ac)
        mv = q * mp
        ur = (mp - ac) * q
        rows.append(
            {
                "심볼": sym,
                "수량": q,
                "평균단가": ac,
                "현재가": mp,
                "평가액": mv,
                "평가손익": ur,
            }
        )
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("보유 종목이 없습니다.")

with right:
    st.subheader("거래 내역 (최신 순)")
    tr = list(reversed(state["trades"]))
    if tr:
        st.dataframe(pd.DataFrame(tr), use_container_width=True, hide_index=True)
    else:
        st.info("체결 내역이 없습니다.")

with st.expander("면책 · 데이터 출처"):
    st.markdown(
        """
        - **교육용 시뮬레이션**입니다. 실제 투자 권유·자문이 아닙니다.
        - 시세·정보는 **yfinance** 등 공개 소스에 의하며 **지연·오류**가 있을 수 있습니다.
        - 체결은 **최근 종가**를 단순 적용한 모델이며 실제 시장과 다릅니다.
        - 브라우저를 닫으면 세션이 초기화될 수 있으니 필요 시 **JSON 저장**을 사용하세요.
        """
    )
