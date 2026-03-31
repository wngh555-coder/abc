"""
Open DART API 공시 데이터 조회 대시보드 (Streamlit)
- 고유번호: corpCode.xml (ZIP) 일별 캐시
- 공시 목록: list.json
인증키: https://opendart.fss.or.kr/ 에서 발급 · 사이드바 입력 또는 .streamlit/secrets.toml 의 DART_API_KEY
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

LIST_URL = "https://opendart.fss.or.kr/api/list.json"
CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
DART_VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="

PBLNTF_TY_OPTIONS = {
    "": "전체",
    "A": "A · 정기공시",
    "B": "B · 주요사항보고",
    "C": "C · 발행공시",
    "D": "D · 지분공시",
    "E": "E · 기타공시",
    "F": "F · 외부감사관련",
    "G": "G · 펀드공시",
    "H": "H · 자산유동화",
    "I": "I · 거래소공시",
    "J": "J · 공정위공시",
}

CORP_CLS_OPTIONS = {
    "": "전체",
    "Y": "Y · 유가증권",
    "K": "K · 코스닥",
    "N": "N · 코넥스",
    "E": "E · 기타",
}

st.set_page_config(
    page_title="Open DART 공시 대시보드",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _http_get_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    q = urllib.parse.urlencode(params)
    full = f"{url}?{q}"
    req = urllib.request.Request(full, headers={"User-Agent": "OpenDartStreamlit/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _dart_status_message(status: str) -> str:
    codes = {
        "000": "정상",
        "010": "등록되지 않은 키",
        "011": "사용할 수 없는 키",
        "012": "접근할 수 없는 IP",
        "013": "조회된 데이터가 없음",
        "014": "파일이 존재하지 않음",
        "020": "요청 제한 초과",
        "021": "조회 가능 회사 수 초과(최대 100건)",
        "100": "필드 값 부적절",
        "101": "부적절한 접근",
        "800": "시스템 점검",
        "900": "정의되지 않은 오류",
        "901": "개인정보 보유기간 만료 키",
    }
    return codes.get(status, status)


@st.cache_data(ttl=86400, show_spinner=False)
def load_corp_master(crtfc_key: str) -> pd.DataFrame:
    """공시대상 회사 고유번호 목록 (ZIP 내 CORPCODE.xml)."""
    q = urllib.parse.urlencode({"crtfc_key": crtfc_key})
    url = f"{CORP_CODE_URL}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "OpenDartStreamlit/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        zdata = resp.read()
    rows: list[dict[str, str]] = []
    with zipfile.ZipFile(io.BytesIO(zdata)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not names:
            return pd.DataFrame()
        with zf.open(names[0]) as xf:
            tree = ET.parse(xf)
    root = tree.getroot()
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag != "corp":
            continue
        code = name = stock = ""
        for child in el:
            ct = child.tag.split("}")[-1]
            if ct == "corp_code":
                code = (child.text or "").strip()
            elif ct == "corp_name":
                name = (child.text or "").strip()
            elif ct == "stock_code":
                stock = (child.text or "").strip()
        if code:
            rows.append({"corp_code": code, "corp_name": name, "stock_code": stock})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["stock_code"] = df["stock_code"].replace("", pd.NA)
    return df


def fetch_disclosure_list(
    crtfc_key: str,
    *,
    corp_code: str | None,
    bgn_de: str,
    end_de: str,
    pblntf_ty: str,
    pblntf_detail_ty: str,
    corp_cls: str,
    last_reprt_at: str,
    sort: str,
    sort_mth: str,
    page_no: int,
    page_count: int,
) -> dict[str, Any]:
    params: dict[str, str] = {
        "crtfc_key": crtfc_key,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_no": str(page_no),
        "page_count": str(min(100, max(1, page_count))),
        "sort": sort or "date",
        "sort_mth": sort_mth or "desc",
    }
    if corp_code:
        params["corp_code"] = corp_code
    if pblntf_ty:
        params["pblntf_ty"] = pblntf_ty
    if pblntf_detail_ty.strip():
        params["pblntf_detail_ty"] = pblntf_detail_ty.strip()
    if corp_cls:
        params["corp_cls"] = corp_cls
    if last_reprt_at in ("Y", "N"):
        params["last_reprt_at"] = last_reprt_at
    return _http_get_json(LIST_URL, params)


st.title("Open DART 공시 대시보드")
st.caption(
    "금융감독원 전자공시 Open API로 공시 목록을 조회합니다. "
    "[개발가이드(공시검색)](https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS001)"
)

with st.sidebar:
    st.header("API 설정")
    secret_key = ""
    try:
        secret_key = st.secrets.get("DART_API_KEY", "") or ""
    except (FileNotFoundError, KeyError, TypeError):
        secret_key = ""
    api_key = st.text_input(
        "Open DART 인증키 (40자)",
        value=secret_key,
        type="password",
        help="비워두면 secrets.toml 의 DART_API_KEY 를 사용합니다.",
    )
    crtfc_key = (api_key or secret_key or "").strip()
    st.divider()
    st.subheader("회사 고유번호")
    st.caption("고유번호 ZIP은 하루 한 번 캐시됩니다. 회사명·종목코드로 검색 후 선택하세요.")
    load_master = st.button("고유번호 목록 불러오기", type="primary", disabled=not crtfc_key)

corp_df = pd.DataFrame()
if crtfc_key and load_master:
    try:
        with st.spinner("고유번호 목록 다운로드 중…"):
            corp_df = load_corp_master(crtfc_key)
        st.session_state["corp_df"] = corp_df
        st.session_state["corp_loaded_key"] = crtfc_key
    except urllib.error.HTTPError as e:
        st.error(f"HTTP 오류: {e.code}")
    except Exception as e:
        st.error(f"고유번호 목록 실패: {e}")

if "corp_df" in st.session_state and st.session_state.get("corp_loaded_key") == crtfc_key:
    corp_df = st.session_state["corp_df"]

selected_corp_code: str | None = None
col_a, col_b = st.columns([1, 1])
with col_a:
    st.subheader("회사 선택 (선택)")
    if corp_df is None or corp_df.empty:
        st.info("사이드바에서 **고유번호 목록 불러오기**를 눌러 주세요. 고유번호 없이 조회 시 기간은 최대 약 3개월로 제한될 수 있습니다.")
        manual_code = st.text_input(
            "고유번호 직접 입력 (8자리)",
            max_chars=8,
            placeholder="예: 00126380",
        )
        if len(manual_code.strip()) == 8:
            selected_corp_code = manual_code.strip()
    else:
        q = st.text_input("회사명 또는 종목코드(6자리) 검색", placeholder="삼성전자 / 005930")
        sub = corp_df
        if q.strip():
            s = q.strip()
            mask = sub["corp_name"].str.contains(s, case=False, na=False)
            if s.isdigit() and len(s) == 6:
                mask = mask | (sub["stock_code"].astype(str).str.replace(".0", "", regex=False) == s)
            elif s.isdigit():
                mask = mask | sub["stock_code"].astype(str).str.contains(s, na=False)
            sub = sub[mask]
        view = sub.head(500).reset_index(drop=True)
        st.caption(f"검색 결과 상위 {len(view):,}건 표시 (전체 마스터 {len(corp_df):,}건)")
        st.dataframe(
            view,
            use_container_width=True,
            hide_index=True,
            column_config={
                "corp_code": st.column_config.TextColumn("고유번호"),
                "corp_name": st.column_config.TextColumn("회사명"),
                "stock_code": st.column_config.TextColumn("종목코드"),
            },
        )
        scope = st.radio(
            "조회 범위",
            ["특정 회사 지정", "고유번호 없이 전체 검색"],
            horizontal=True,
            help="고유번호가 없으면 API에서 검색 기간이 짧게 제한될 수 있습니다.",
        )
        if scope == "특정 회사 지정" and len(view) > 0:
            labels = [
                f"{r['corp_name']} | 종목 {r['stock_code'] or '-'} | {r['corp_code']}"
                for _, r in view.iterrows()
            ]
            choice = st.selectbox("조회할 회사 선택", options=range(len(labels)), format_func=lambda i: labels[i])
            row = view.iloc[int(choice)]
            selected_corp_code = str(row["corp_code"])
            st.success(f"선택: **{row['corp_name']}** (`{selected_corp_code}`)")
        elif scope == "특정 회사 지정" and len(view) == 0:
            st.warning("검색 조건에 맞는 회사가 없습니다. 검색어를 바꾸거나 **고유번호 없이 전체 검색**을 사용하세요.")

with col_b:
    st.subheader("조회 조건")
    today = date.today()
    default_end = today
    default_start = today - timedelta(days=90)
    dr = st.date_input(
        "접수일 범위",
        value=(default_start, default_end),
        max_value=today,
    )
    if isinstance(dr, tuple) and len(dr) == 2:
        bgn_de, end_de = dr[0].strftime("%Y%m%d"), dr[1].strftime("%Y%m%d")
    else:
        bgn_de = end_de = today.strftime("%Y%m%d")

    pblntf_ty = st.selectbox("공시유형", options=list(PBLNTF_TY_OPTIONS.keys()), format_func=lambda k: PBLNTF_TY_OPTIONS[k])
    pblntf_detail_ty = st.text_input("공시상세유형 (선택, 예: A001 사업보고서)", placeholder="비우면 전체")
    corp_cls = st.selectbox("법인구분", options=list(CORP_CLS_OPTIONS.keys()), format_func=lambda k: CORP_CLS_OPTIONS[k])
    last_reprt = st.selectbox("최종보고서만", options=["N", "Y"], format_func=lambda x: "아니오 (기본)" if x == "N" else "예")
    sort_col = st.selectbox("정렬", options=["date", "crp", "rpt"], format_func=lambda x: {"date": "접수일", "crp": "회사명", "rpt": "보고서명"}[x])
    sort_mth = st.selectbox("정렬순서", options=["desc", "asc"], format_func=lambda x: "내림차순" if x == "desc" else "오름차순")
    page_no = st.number_input("페이지", min_value=1, value=1, step=1)
    page_count = st.slider("페이지당 건수", min_value=10, max_value=100, value=20, step=10)

run = st.button("공시 조회", type="primary", disabled=not crtfc_key)

if run and crtfc_key:
    try:
        with st.spinner("공시 목록 조회 중…"):
            data = fetch_disclosure_list(
                crtfc_key,
                corp_code=selected_corp_code,
                bgn_de=bgn_de,
                end_de=end_de,
                pblntf_ty=pblntf_ty,
                pblntf_detail_ty=pblntf_detail_ty,
                corp_cls=corp_cls,
                last_reprt_at=last_reprt,
                sort=sort_col,
                sort_mth=sort_mth,
                page_no=int(page_no),
                page_count=int(page_count),
            )
        status = str(data.get("status", ""))
        if status != "000":
            st.error(f"API 오류 [{status}]: {data.get('message', '')} — {_dart_status_message(status)}")
        else:
            items = data.get("list") or []
            total_count = int(data.get("total_count") or 0)
            total_page = int(data.get("total_page") or 0)
            st.success(
                f"총 **{total_count:,}**건 · 페이지 **{data.get('page_no', page_no)}** / **{total_page}** "
                f"(이 페이지 {len(items)}건)"
            )
            if not items:
                st.warning("이 조건으로는 결과가 없습니다.")
            else:
                df = pd.DataFrame(items)
                rename = {
                    "corp_name": "회사명",
                    "stock_code": "종목코드",
                    "corp_code": "고유번호",
                    "corp_cls": "법인구분",
                    "report_nm": "보고서명",
                    "rcept_no": "접수번호",
                    "rcept_dt": "접수일자",
                    "flr_nm": "제출인",
                    "rm": "비고",
                }
                show = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
                if "접수번호" in show.columns:
                    show["공시 바로가기"] = show["접수번호"].astype(str).map(lambda r: f"{DART_VIEWER}{r}")
                st.dataframe(
                    show,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "공시 바로가기": st.column_config.LinkColumn("DART 원문"),
                    },
                )
                if "접수일자" in show.columns and len(show) > 1:
                    cnt = show.groupby("접수일자", as_index=False).size()
                    fig = px.bar(cnt, x="접수일자", y="size", labels={"size": "건수"}, title="일자별 공시 건수(현재 페이지)")
                    st.plotly_chart(fig, use_container_width=True)
    except urllib.error.HTTPError as e:
        st.error(f"HTTP 오류: {e.code}")
    except json.JSONDecodeError:
        st.error("응답이 JSON이 아닙니다. 인증키·URL을 확인하세요.")
    except Exception as e:
        st.error(f"조회 실패: {e}")

elif run and not crtfc_key:
    st.warning("사이드바에 Open DART 인증키를 입력하거나 `.streamlit/secrets.toml`에 `DART_API_KEY`를 설정하세요.")

st.divider()
st.markdown(
    """
**참고**
- 인증키 발급: [Open DART — 인증키 신청](https://opendart.fss.or.kr/uss/umt/EgovMberInsertView.do)
- `고유번호` 없이 조회 시 API 정책상 검색 기간이 짧게 제한될 수 있습니다.
- 상세 공시유형 코드는 [공시검색 개발가이드](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001)의 `pblntf_detail_ty` 표를 참고하세요.
"""
)
