"""
엔비디아(NVDA) 주가 대시보드 — yfinance + Streamlit + Plotly
실행: streamlit run nvidia_dashboard.py
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf

TICKER = "NVDA"
COMPANY_NAME = "NVIDIA Corporation"

st.set_page_config(
    page_title=f"{TICKER} 주가 대시보드",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=300)
def fetch_history(
    symbol: str,
    period: str,
    interval: str,
) -> pd.DataFrame:
    t = yf.Ticker(symbol)
    df = t.history(period=period, interval=interval, auto_adjust=True)
    if df.empty:
        return df
    df = df.rename_axis("Date").reset_index()
    if pd.api.types.is_datetime64_any_dtype(df["Date"]):
        df["Date"] = df["Date"].dt.tz_localize(None)
    return df


@st.cache_data(ttl=600)
def fetch_info(symbol: str) -> dict:
    t = yf.Ticker(symbol)
    return t.info or {}


def add_ma(df: pd.DataFrame, windows: tuple[int, ...]) -> pd.DataFrame:
    out = df.copy()
    for w in windows:
        out[f"MA{w}"] = out["Close"].rolling(window=w, min_periods=1).mean()
    return out


def build_candle_volume_fig(df: pd.DataFrame, show_ma: bool) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.72, 0.28],
    )
    fig.add_trace(
        go.Candlestick(
            x=df["Date"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="OHLC",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        row=1,
        col=1,
    )
    if show_ma and "MA20" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["Date"],
                y=df["MA20"],
                name="MA20",
                line=dict(color="#ff9800", width=1.5),
            ),
            row=1,
            col=1,
        )
    if show_ma and "MA50" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["Date"],
                y=df["MA50"],
                name="MA50",
                line=dict(color="#2196f3", width=1.5),
            ),
            row=1,
            col=1,
        )
    colors = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(
        go.Bar(
            x=df["Date"],
            y=df["Volume"],
            name="거래량",
            marker_color=colors,
            opacity=0.7,
        ),
        row=2,
        col=1,
    )
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=640,
        margin=dict(l=48, r=24, t=48, b=48),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_dark",
    )
    fig.update_yaxes(title_text="가격 (USD)", row=1, col=1)
    fig.update_yaxes(title_text="거래량", row=2, col=1)
    return fig


def add_volume_ma(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    out = df.copy()
    col = f"VolMA{window}"
    out[col] = out["Volume"].rolling(window=window, min_periods=1).mean()
    return out, col


def ma_cross_label(ma_fast: pd.Series, ma_slow: pd.Series, max_lookback: int = 10) -> tuple[str, int]:
    """최근 골든/데드크로스 여부와 점수 기여(-15~15)."""
    diff = ma_fast - ma_slow
    if len(diff) < 2 or diff.isna().all():
        return "데이터 부족", 0
    score = 0
    label = "정배열/역배열 유지"
    for k in range(1, min(max_lookback, len(diff))):
        a, b = diff.iloc[-(k + 1)], diff.iloc[-k]
        if pd.isna(a) or pd.isna(b):
            continue
        if a <= 0 < b:
            label = f"최근 골든크로스 (약 {k}봉 전)"
            score = 12
            break
        if a >= 0 > b:
            label = f"최근 데드크로스 (약 {k}봉 전)"
            score = -12
            break
    if score == 0:
        if diff.iloc[-1] > 0:
            label = "단기 이평 > 장기 이평 (정배열)"
            score = 6
        elif diff.iloc[-1] < 0:
            label = "단기 이평 < 장기 이평 (역배열)"
            score = -6
    return label, score


def volume_momentum_score(
    close: float,
    prev_close: float,
    vol: float,
    vol_ma: float,
) -> tuple[str, int]:
    if vol_ma is None or pd.isna(vol_ma) or vol_ma <= 0 or pd.isna(vol):
        return "거래량 기준 불가", 0
    ratio = vol / vol_ma
    up = close >= prev_close
    if ratio >= 1.25:
        if up:
            return f"거래량 급증({ratio:.2f}×) + 상승 봉 — 추세 확인 신호", 10
        return f"거래량 급증({ratio:.2f}×) + 하락 봉 — 분산·조정 압력 가능", -10
    if ratio <= 0.75:
        return f"거래량 감소({ratio:.2f}×) — 관망·추세 약화 가능", -3 if up else 3
    return f"거래량 평균 수준 ({ratio:.2f}×)", 0


def outlook_from_ma_volume(df: pd.DataFrame) -> dict:
    """이동평균·거래량 기반 규칙형 전망 요약 (참고용, 투자 조언 아님)."""
    row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else row
    close = float(row["Close"])
    pclose = float(prev["Close"])

    reasons: list[str] = []
    score = 0

    if "MA20" in df.columns and "MA50" in df.columns:
        ma20, ma50 = row["MA20"], row["MA50"]
        if pd.notna(ma20) and pd.notna(ma50):
            cross_txt, cross_pts = ma_cross_label(df["MA20"], df["MA50"])
            reasons.append(cross_txt)
            score += cross_pts
            if close > ma20:
                reasons.append("종가가 MA20 위 — 단기 모멘텀 양호")
                score += 8
            else:
                reasons.append("종가가 MA20 아래 — 단기 약세 구간")
                score -= 8
            if close > ma50:
                reasons.append("종가가 MA50 위 — 중기 기준선 위")
                score += 8
            else:
                reasons.append("종가가 MA50 아래 — 중기 기준선 아래")
                score -= 8

    df_v, vol_ma_col = add_volume_ma(df, 20)
    vrow = df_v.iloc[-1]
    vol = float(vrow["Volume"]) if pd.notna(vrow["Volume"]) else float("nan")
    vol_ma = float(vrow[vol_ma_col]) if vol_ma_col in vrow.index else float("nan")
    vtxt, vpts = volume_momentum_score(close, pclose, vol, vol_ma)
    reasons.append(vtxt)
    score += vpts

    score = max(-100, min(100, score))
    if score >= 18:
        label, tone = "상승 우세 (기술적)", "bull"
    elif score <= -18:
        label, tone = "하락 우세 (기술적)", "bear"
    else:
        label, tone = "중립·혼조 (기술적)", "neutral"

    return {
        "score": score,
        "label": label,
        "tone": tone,
        "reasons": reasons,
        "vol_ratio": (vol / vol_ma) if vol_ma and not np.isnan(vol) and vol_ma > 0 else None,
    }


def _calendar_step_days(sub: pd.DataFrame) -> int:
    if len(sub) < 2:
        return 1
    deltas = sub["Date"].diff().dt.days.dropna()
    if deltas.empty:
        return 1
    return max(1, int(round(float(deltas.median()))))


def linear_price_forecast(
    df: pd.DataFrame,
    horizon: int,
    lookback: int,
    *,
    volume_weighted: bool = False,
    band_sigma: float = 1.96,
) -> tuple[
    pd.Series,
    pd.Series,
    pd.Series,
    pd.Series,
    pd.Series,
    pd.Series,
    float,
    float,
    float,
]:
    """
    최근 lookback 종가에 대한 1차 선형 회귀(선택: 거래량 가중) 후 horizon 봉 외삽.
    반환: 과거 날짜, 적합 종가, 미래 날짜, 예측 종가, 상단 밴드, 하단 밴드, slope, intercept, 잔차 표준편차
    """
    empty_t = pd.Series(dtype="datetime64[ns]")
    empty_v = pd.Series(dtype=float)
    need = ["Close", "Date", "Volume"] if volume_weighted else ["Close", "Date"]
    sub = df.tail(lookback).dropna(subset=need)
    if len(sub) < 5:
        return empty_t, empty_v, empty_t, empty_v, empty_v, empty_v, 0.0, 0.0, 0.0
    y = sub["Close"].to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)
    if volume_weighted:
        vol = sub["Volume"].to_numpy(dtype=float)
        med_v = float(np.nanmedian(vol[vol > 0])) if np.any(vol > 0) else 1.0
        vol = np.where(vol <= 0, med_v, vol)
        w = np.sqrt(vol / np.mean(vol))
        slope, intercept = np.polyfit(x, y, 1, w=w)
    else:
        slope, intercept = np.polyfit(x, y, 1)
    fit = slope * x + intercept
    resid = y - fit
    sigma = float(np.std(resid, ddof=min(2, len(resid) - 1))) if len(resid) > 2 else float(np.std(resid))

    last_dt = pd.Timestamp(sub["Date"].iloc[-1])
    step = _calendar_step_days(sub)

    future_dates = pd.Series(
        [last_dt + pd.Timedelta(days=step * i) for i in range(1, horizon + 1)]
    )
    x_future = np.arange(len(y), len(y) + horizon, dtype=float)
    forecast = slope * x_future + intercept
    # 단순 불확실성: 잔차 분산을 시간에 따라 완만히 키우는 참고용 밴드
    k = np.arange(1, horizon + 1, dtype=float)
    widen = np.sqrt(1.0 + k / max(len(y), 1))
    upper = forecast + band_sigma * sigma * widen
    lower = forecast - band_sigma * sigma * widen

    hist_dates = sub["Date"].reset_index(drop=True)
    hist_fit = pd.Series(fit)
    fc_series = pd.Series(forecast)
    return (
        hist_dates,
        hist_fit,
        future_dates,
        fc_series,
        pd.Series(upper),
        pd.Series(lower),
        float(slope),
        float(intercept),
        sigma,
    )


def build_outlook_figure(
    df: pd.DataFrame,
    future_dates: pd.Series,
    forecast: pd.Series,
    hist_fit_dates: pd.Series,
    hist_fit: pd.Series,
    upper: pd.Series | None = None,
    lower: pd.Series | None = None,
    forecast_label: str = "추세 외삽(참고)",
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["Date"],
            y=df["Close"],
            name="종가",
            line=dict(color="#76ff03", width=2),
        )
    )
    if "MA20" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["Date"],
                y=df["MA20"],
                name="MA20",
                line=dict(color="#ff9800", width=1.2),
            )
        )
    if "MA50" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["Date"],
                y=df["MA50"],
                name="MA50",
                line=dict(color="#2196f3", width=1.2),
            )
        )
    if len(hist_fit_dates) and len(hist_fit):
        fig.add_trace(
            go.Scatter(
                x=hist_fit_dates,
                y=hist_fit,
                name="추세 적합(선형)",
                line=dict(color="#ab47bc", width=2, dash="dot"),
            )
        )
    if len(future_dates) and len(forecast):
        last_close = float(df["Close"].iloc[-1])
        first_fc = float(forecast.iloc[0])
        if (
            upper is not None
            and lower is not None
            and len(upper) == len(forecast)
            and len(lower) == len(forecast)
        ):
            x_band = pd.concat([future_dates, future_dates[::-1]], ignore_index=True)
            y_band = pd.concat([upper, lower[::-1]], ignore_index=True)
            fig.add_trace(
                go.Scatter(
                    x=x_band,
                    y=y_band,
                    fill="toself",
                    fillcolor="rgba(251, 192, 45, 0.15)",
                    line=dict(color="rgba(0,0,0,0)"),
                    name="예측 참고 구간",
                    hoverinfo="skip",
                )
            )
        fig.add_trace(
            go.Scatter(
                x=[df["Date"].iloc[-1], future_dates.iloc[0]],
                y=[last_close, first_fc],
                mode="lines",
                line=dict(color="#fbc02d", width=2, dash="dash"),
                name="전환(참고)",
                showlegend=True,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=future_dates,
                y=forecast,
                name=forecast_label,
                line=dict(color="#fbc02d", width=2, dash="dash"),
            )
        )
    fig.update_layout(
        template="plotly_dark",
        height=420,
        margin=dict(l=48, r=24, t=40, b=48),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title="날짜",
        yaxis_title="USD",
    )
    return fig


def build_volume_outlook_fig(df: pd.DataFrame, vol_ma_window: int = 20) -> go.Figure:
    """거래량 vs 이동평균 거래량 — 전망 섹션용."""
    sub = df.dropna(subset=["Volume", "Date"]).copy()
    col = f"VolMA{vol_ma_window}"
    sub[col] = sub["Volume"].rolling(window=vol_ma_window, min_periods=1).mean()
    colors = [
        "#26a69a" if c >= o else "#ef5350"
        for o, c in zip(sub["Open"], sub["Close"])
    ]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=sub["Date"],
            y=sub["Volume"],
            name="거래량",
            marker_color=colors,
            opacity=0.65,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=sub["Date"],
            y=sub[col],
            name=f"거래량 MA{vol_ma_window}",
            line=dict(color="#ffd54f", width=2),
        )
    )
    fig.update_layout(
        template="plotly_dark",
        height=280,
        margin=dict(l=48, r=24, t=32, b=48),
        xaxis_title="날짜",
        yaxis_title="거래량",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


st.title(f"📈 {COMPANY_NAME} ({TICKER})")
st.caption("yfinance 실시간에 가까운 시세 · 사이드바에서 기간·간격을 바꿔 확인합니다.")

with st.sidebar:
    st.header("설정")
    period = st.selectbox(
        "조회 기간",
        options=["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"],
        format_func=lambda x: {
            "1mo": "1개월",
            "3mo": "3개월",
            "6mo": "6개월",
            "1y": "1년",
            "2y": "2년",
            "5y": "5년",
            "max": "전체",
        }[x],
        index=3,
    )
    interval = st.selectbox(
        "봉 간격",
        options=["1d", "1wk", "1mo"],
        format_func=lambda x: {"1d": "일봉", "1wk": "주봉", "1mo": "월봉"}[x],
        index=0,
    )
    show_ma = st.checkbox("이동평균선 (20·50 봉)", value=True)
    st.divider()
    st.subheader("전망·예측")
    forecast_horizon = st.slider(
        "추세 외삽 구간 (봉 수)",
        min_value=3,
        max_value=30,
        value=10,
        help="최근 종가에 직선을 맞춘 뒤 같은 기울기로 연장한 참고선입니다.",
    )
    forecast_lookback = st.selectbox("회귀에 쓸 과거 봉 수", [20, 40, 60, 90, 120], index=2)
    vol_weighted_fc = st.checkbox(
        "예측: 거래량 가중 회귀",
        value=True,
        help="최근 봉일수록 거래량이 큰 날의 종가에 더 큰 가중을 둡니다.",
    )
    st.divider()
    st.caption("데이터는 Yahoo Finance를 통해 제공됩니다. 시장 휴장일은 봉이 없을 수 있습니다.")

hist = fetch_history(TICKER, period=period, interval=interval)
info = fetch_info(TICKER)

if hist.empty:
    st.error("주가 데이터를 불러오지 못했습니다. 네트워크 또는 티커를 확인해 주세요.")
    st.stop()

if show_ma:
    hist = add_ma(hist, (20, 50))

last = hist.iloc[-1]
prev_close = hist.iloc[-2]["Close"] if len(hist) > 1 else last["Close"]
chg = last["Close"] - prev_close
chg_pct = (chg / prev_close * 100) if prev_close else 0.0

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "종가 (USD)",
    f"{last['Close']:.2f}",
    f"{chg:+.2f} ({chg_pct:+.2f}%)",
)
col2.metric("고가", f"{last['High']:.2f}")
col3.metric("저가", f"{last['Low']:.2f}")
vol_str = f"{int(last['Volume']):,}" if pd.notna(last["Volume"]) else "—"
col4.metric("거래량", vol_str)

if info:
    mc = info.get("marketCap")
    cap_str = f"{mc / 1e9:.1f}B USD" if mc else "—"
    h52 = info.get("fiftyTwoWeekHigh")
    l52 = info.get("fiftyTwoWeekLow")
    pe = info.get("trailingPE")
    high52 = f"{h52:.2f}" if h52 is not None else "—"
    low52 = f"{l52:.2f}" if l52 is not None else "—"
    pe_str = f"{pe:.2f}" if pe is not None else "—"
    with st.expander("기업 요약 (yfinance info)", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.write(
                f"**섹터:** {info.get('sector', '—')}  \n"
                f"**산업:** {info.get('industry', '—')}  \n"
                f"**시가총액:** {cap_str}"
            )
        with c2:
            st.write(
                f"**52주 최고:** {high52}  \n"
                f"**52주 최저:** {low52}  \n"
                f"**PER (ttm):** {pe_str}"
            )
        summary = info.get("longBusinessSummary") or info.get("shortName")
        if summary:
            st.markdown(str(summary)[:1200] + ("…" if len(str(summary)) > 1200 else ""))

st.subheader("캔들 · 거래량")
fig = build_candle_volume_fig(hist, show_ma=show_ma)
st.plotly_chart(fig, use_container_width=True)

st.subheader("종가 추이 (라인)")
line_fig = go.Figure()
line_fig.add_trace(
    go.Scatter(
        x=hist["Date"],
        y=hist["Close"],
        mode="lines",
        name="종가",
        line=dict(color="#76ff03", width=2),
        fill="tozeroy",
        fillcolor="rgba(118, 255, 3, 0.08)",
    )
)
line_fig.update_layout(
    template="plotly_dark",
    height=360,
    margin=dict(l=48, r=24, t=32, b=48),
    xaxis_title="날짜",
    yaxis_title="USD",
)
st.plotly_chart(line_fig, use_container_width=True)

st.divider()
st.subheader("기술적 전망·추세 참고")
st.info(
    "이 구간은 **이동평균·거래량 규칙**과 **단순 선형 추세 외삽**으로 만든 참고용 요약입니다. "
    "실제 시장·뉴스·실적 등을 반영하지 않으며, 투자 권유나 수익 보장이 아닙니다."
)

hist_for_signal = hist.copy()
if "MA20" not in hist_for_signal.columns:
    hist_for_signal = add_ma(hist_for_signal, (20, 50))

outlook = outlook_from_ma_volume(hist_for_signal)
tone_emoji = {"bull": "🟢", "bear": "🔴", "neutral": "🟡"}.get(outlook["tone"], "⚪")
o1, o2, o3 = st.columns(3)
o1.metric("기술적 성향", f"{tone_emoji} {outlook['label']}")
o2.metric("규칙 기반 점수", f"{outlook['score']:+d}", help="이동평균 배열·종가 위치·거래량 대비 등 가중 합(대략 -100~100)")
vr = outlook["vol_ratio"]
o3.metric(
    "최근 거래량 / 20봉 평균",
    f"{vr:.2f}×" if vr is not None else "—",
)

st.caption("규칙 점수 스케일 (대략 -100 ~ +100)")
st.progress(min(1.0, max(0.0, (outlook["score"] + 100) / 200.0)))

st.markdown("**판단 근거 (규칙 요약)**")
for r in outlook["reasons"]:
    st.markdown(f"- {r}")

lookback_use = min(forecast_lookback, len(hist))
hd, hf, fd, fc, fc_up, fc_lo, slope, _intercept, sigma_fc = linear_price_forecast(
    hist,
    forecast_horizon,
    lookback_use,
    volume_weighted=vol_weighted_fc,
)
if len(fd) >= 1 and len(fc) >= 1:
    slope_txt = "상승 추세(참고)" if slope > 0 else ("하락 추세(참고)" if slope < 0 else "횡보에 가까움")
    wtxt = "거래량 가중" if vol_weighted_fc else "일반 최소제곱"
    st.caption(
        f"아래 점선은 최근 **{lookback_use}봉** 종가에 **{wtxt}** 선형 회귀를 맞춘 뒤 **{forecast_horizon}봉**으로 외삽한 참고값입니다. "
        f"음영은 잔차 표준편차 기반 **참고 구간**(통계적 신뢰구간과 다름). "
        f"기울기: **{slope_txt}** (봉당 약 {slope:+.4f} USD), 잔차 σ≈{sigma_fc:.3f}"
    )
    fc_label = "추세 외삽 (거래량 가중)" if vol_weighted_fc else "추세 외삽 (동일 가중)"
    fig_o = build_outlook_figure(
        hist_for_signal,
        fd,
        fc,
        hd,
        hf,
        upper=fc_up,
        lower=fc_lo,
        forecast_label=fc_label,
    )
    st.plotly_chart(fig_o, use_container_width=True)

    st.markdown("**거래량 맥락 (MA20 대비)**")
    st.plotly_chart(build_volume_outlook_fig(hist_for_signal, 20), use_container_width=True)

    last_c = float(hist["Close"].iloc[-1])
    end_fc = float(fc.iloc[-1])
    pct_chg = (end_fc - last_c) / last_c * 100 if last_c else 0.0
    ma_gap = None
    if "MA20" in hist_for_signal.columns and pd.notna(hist_for_signal["MA20"].iloc[-1]):
        ma20l = float(hist_for_signal["MA20"].iloc[-1])
        ma_gap = (last_c - ma20l) / ma20l * 100
    sum_cols = {
        "구분": [
            "마지막 실제 종가",
            "외삽 종가(참고, 마지막 봉)",
            "예측 변화율(참고)",
            "종가 vs MA20 괴리(%)",
        ],
        "값": [
            f"{last_c:.2f} USD",
            f"{end_fc:.2f} USD",
            f"{pct_chg:+.2f}%",
            f"{ma_gap:+.2f}%" if ma_gap is not None else "—",
        ],
    }
    st.dataframe(pd.DataFrame(sum_cols), use_container_width=True, hide_index=True)

    fc_tbl = pd.DataFrame(
        {
            "예상일(캘린더)": [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d) for d in fd],
            "참고 종가": [f"{v:.2f}" for v in fc],
            "참고 상단": [f"{v:.2f}" for v in fc_up],
            "참고 하단": [f"{v:.2f}" for v in fc_lo],
        }
    )
    with st.expander("봉별 외삽 표 (참고)", expanded=False):
        st.dataframe(fc_tbl, use_container_width=True, hide_index=True)
else:
    st.warning("추세 외삽 차트를 그리기에 데이터가 부족합니다. 조회 기간을 늘리거나 봉 간격을 확인해 주세요.")

st.subheader("최근 데이터")
display_cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
extra = [c for c in ("MA20", "MA50") if c in hist.columns]
st.dataframe(
    hist[display_cols + extra].sort_values("Date", ascending=False).head(200),
    use_container_width=True,
    height=320,
)

st.caption(
    f"마지막 봉 기준일: {last['Date'] if hasattr(last['Date'], 'strftime') else last['Date']} · "
    "투자 판단에 앞서 공식 공시·증권사 리포트를 함께 확인하세요."
)
