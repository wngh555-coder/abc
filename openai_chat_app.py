"""
OpenAI Chat Completions API 기반 챗봇 (Streamlit).

로컬:
  `.streamlit/secrets.toml`에 OPENAI_API_KEY 설정 후
  `streamlit run openai_chat_app.py`
  (포트 지정 예: `--server.port 8509`)

Streamlit Community Cloud (share.streamlit.io):
  GitHub 연동 후 앱 설정 → Main file: `openai_chat_app.py`
  → Secrets에 OPENAI_API_KEY = "sk-..." 형식으로 등록
"""

from __future__ import annotations

import os
from typing import Any, Generator

import streamlit as st
from openai import OpenAI


def _api_key() -> str | None:
    """로컬 secrets.toml → Cloud Secrets → 환경 변수 순."""
    try:
        sec = st.secrets
        if "OPENAI_API_KEY" in sec:
            v = sec["OPENAI_API_KEY"]
            if v:
                return str(v).strip() or None
    except (FileNotFoundError, RuntimeError, KeyError, TypeError, AttributeError):
        pass
    return os.environ.get("OPENAI_API_KEY", "").strip() or None


@st.cache_resource(show_spinner=False)
def _cached_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def _chat_stream(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
) -> Generator[str, None, None]:
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


st.set_page_config(
    page_title="OpenAI 챗봇",
    page_icon="💬",
    layout="centered",
    initial_sidebar_state="expanded",
)

st.title("💬 OpenAI 챗봇")
st.caption("Chat Completions API · 스트리밍 응답")

with st.sidebar:
    st.header("설정")
    model = st.selectbox(
        "모델",
        options=[
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4-turbo",
        ],
        index=0,
        help="비용·속도에 맞게 선택하세요.",
    )
    temperature = st.slider(
        "온도 (temperature)",
        min_value=0.0,
        max_value=2.0,
        value=0.7,
        step=0.05,
        help="낮을수록 일관적, 높을수록 다양한 응답",
    )
    system_prompt = st.text_area(
        "시스템 프롬프트",
        value="당신은 친절하고 정확하게 답하는 도우미입니다.",
        height=120,
    )
    if st.button("대화 초기화", type="secondary"):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.markdown(
        "**Community Cloud 배포 시:** 앱 → Settings → Secrets에 "
        "`OPENAI_API_KEY`를 넣어 주세요."
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

api_key = _api_key()
if not api_key:
    st.error("OpenAI API 키가 없습니다.")
    st.info(
        "- **로컬:** 저장소 루트에 `.streamlit/secrets.toml`을 만들고 "
        "`OPENAI_API_KEY = \"sk-...\"` 를 넣거나, 환경 변수 `OPENAI_API_KEY`를 설정하세요.\n"
        "- **Streamlit Community Cloud:** 웹에서 앱 → **Settings** → **Secrets**에 "
        "같은 키를 추가하세요."
    )
    st.stop()

client = _cached_client(api_key)

if prompt := st.chat_input("메시지를 입력하세요…"):
    st.session_state.messages.append({"role": "user", "content": prompt})

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 마지막이 사용자 메시지면 어시스턴트 응답 생성
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    api_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    api_messages.extend(st.session_state.messages)

    with st.chat_message("assistant"):
        _chunks: list[str] = []

        def _gen() -> Generator[str, None, None]:
            for piece in _chat_stream(
                client,
                model=model,
                messages=api_messages,
                temperature=temperature,
            ):
                _chunks.append(piece)
                yield piece

        try:
            written = st.write_stream(_gen())
            full = written if written else "".join(_chunks)
        except Exception as e:
            st.error(f"API 오류: {e}")
            full = ""

    if full:
        st.session_state.messages.append({"role": "assistant", "content": full})
