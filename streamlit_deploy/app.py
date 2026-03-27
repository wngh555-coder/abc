"""
Streamlit Community Cloud에서 Main file을 `streamlit_deploy/app.py`로 둘 때 사용하는 진입점.

권장: 저장소 루트의 `openai_chat_app.py`를 Main file로 지정하면 이 파일은 필요 없습니다.
"""

from __future__ import annotations

import runpy
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
runpy.run_path(str(_ROOT / "openai_chat_app.py"), run_name="__main__")
