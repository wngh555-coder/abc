"""
Streamlit Community Cloud 기본 진입 이름으로 쓰기 위한 얇은 래퍼.

Main file을 `streamlit_app.py`로 두면 루트의 `openai_chat_app.py`를 실행합니다.
동일 앱을 `openai_chat_app.py`로 직접 지정해도 됩니다.
"""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "openai_chat_app.py"), run_name="__main__")
