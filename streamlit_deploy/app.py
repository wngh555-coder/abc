"""
Streamlit Community Cloud 진입점.

Main file: `streamlit_deploy/app.py` 로 지정하면 인생 시뮬레이터가 실행됩니다.
로컬(저장소 루트에서): `streamlit run streamlit_deploy/app.py`
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

runpy.run_path(str(_HERE / "life_sim_app.py"), run_name="__main__")
