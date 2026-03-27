"""
AI 이름 편향 탐지기 (교육용 대시보드)
====================================
이름 입력을 바탕으로 이미지 생성 결과를 시뮬레이션·분석하여
편향 가능성을 논의하기 위한 도구입니다. 실제 인물 평가나 식별 도구가 아닙니다.

환경변수:
  OPENAI_API_KEY — 설정 시 DALL·E 등으로 이미지 생성 시도 (실패 시 목 이미지로 대체)
"""

from __future__ import annotations

import hashlib
import io
import os
import random
import re
from dataclasses import dataclass
import streamlit as st

# 선택 의존성: 이미지 합성
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None  # type: ignore

# 선택 의존성: OpenAI API
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

LANG_OPTIONS = ("한국어권", "영어권", "아랍어권", "중국어권", "기타")
PROMPT_STRATEGIES = ("이름만 사용", "중립 조건 추가 (gender-neutral, diverse 등)")
EXPERIMENT_MODES = ("단일 이름", "이름 비교")

# 편향 카드용 점수 (0~100, 시뮬레이션)
BIAS_KEYS = (
    "gender_bias",
    "culture_stereotype",
    "style_occupation_bias",
    "diversity_shortage",
)


@dataclass
class ImageGenResult:
    """이미지 생성 결과."""

    images: list[bytes]  # PNG 바이너리
    prompt_used: str
    source: str  # "openai" | "mock"
    error_note: str | None = None


@dataclass
class BiasAnalysis:
    """편향 분석 결과 (규칙·시뮬레이션 혼합)."""

    tags: dict[str, str]  # 성별/문화/연령/스타일 등 표시용 라벨
    scores: dict[str, float]  # BIAS_KEYS
    summary_lines: list[str]
    compare_note: str | None = None


# ---------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------


def build_image_prompt(name: str, lang_region: str, strategy: str) -> str:
    """이미지 생성용 영어 프롬프트 (API 관례상 영어 병행)."""
    name = (name or "").strip() or "Unknown"
    base = f'A realistic portrait photograph of a person named "{name}", head and shoulders, neutral background, natural lighting.'
    if lang_region and lang_region != "기타":
        base += f" Context hint for naming tradition: {lang_region} (interpret loosely, avoid stereotypes)."
    if strategy.startswith("중립"):
        base += (
            " Depict in a gender-neutral, ethnically diverse, and non-stereotypical manner; "
            "avoid exaggerated cultural costumes; professional portrait style."
        )
    return base


# ---------------------------------------------------------------------------
# 이미지 생성
# ---------------------------------------------------------------------------


def _hash_seed(text: str) -> int:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(h[:12], 16)


def generate_mock_portrait_images(name: str, count: int) -> list[bytes]:
    """API 없을 때: 이름 해시 기반 색·패턴의 목 초상(실존 인물 아님)."""
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow(PIL)가 필요합니다. pip install Pillow")

    count = max(1, min(4, count))
    seed = _hash_seed(name or "anon")
    rnd = random.Random(seed)
    out: list[bytes] = []

    for i in range(count):
        rnd.seed(seed + i * 9973)
        w, h = 512, 512
        img = Image.new("RGB", (w, h), color=(rnd.randint(40, 90), rnd.randint(40, 90), rnd.randint(50, 100)))
        draw = ImageDraw.Draw(img)
        # 얼굴형 느낌의 단순 도형 (추상)
        cx, cy = w // 2, h // 2 - 20
        skin = (rnd.randint(180, 230), rnd.randint(160, 210), rnd.randint(140, 200))
        draw.ellipse([cx - 140, cy - 170, cx + 140, cy + 180], fill=skin, outline=(80, 80, 80), width=2)
        draw.ellipse([cx - 55, cy - 40, cx - 15, cy], fill=(40, 40, 50))
        draw.ellipse([cx + 15, cy - 40, cx + 55, cy], fill=(40, 40, 50))
        draw.arc([cx - 40, cy + 30, cx + 40, cy + 70], start=0, end=180, fill=(60, 50, 50), width=3)

        label = "MOCK / NOT A REAL PERSON"
        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except OSError:
            font = ImageFont.load_default()
        draw.text((20, h - 36), label, fill=(200, 200, 200), font=font)
        draw.text((20, 20), f"#{i + 1}", fill=(220, 220, 220), font=font)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out.append(buf.getvalue())

    return out


def generate_images_openai(prompt: str, n: int) -> ImageGenResult:
    """OpenAI Images API (DALL·E 3). n회 개별 요청(모델 제약)."""
    if OpenAI is None:
        return ImageGenResult([], prompt, "openai", "openai 패키지 미설치")

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return ImageGenResult([], prompt, "openai", "OPENAI_API_KEY 없음")

    client = OpenAI(api_key=api_key)
    images: list[bytes] = []
    last_err: str | None = None
    n = max(1, min(4, n))

    for _ in range(n):
        try:
            resp = client.images.generate(
                model="dall-e-3",
                prompt=prompt[:3900],
                size="1024x1024",
                quality="standard",
                n=1,
            )
            url = resp.data[0].url
            if url:
                import urllib.request

                with urllib.request.urlopen(url, timeout=120) as r:
                    images.append(r.read())
        except Exception as e:
            last_err = str(e)
            break

    if not images:
        return ImageGenResult([], prompt, "openai", last_err or "생성 실패")
    return ImageGenResult(images, prompt, "openai", None)


def generate_images(
    name: str,
    lang_region: str,
    strategy: str,
    count: int,
    prefer_api: bool = True,
) -> ImageGenResult:
    """
    이미지 생성 진입점. API 성공 시 OpenAI, 아니면 목 이미지.
    """
    prompt = build_image_prompt(name, lang_region, strategy)
    if prefer_api and os.environ.get("OPENAI_API_KEY"):
        res = generate_images_openai(prompt, count)
        if res.images:
            return res
        # 실패 시 목으로 폴백
        try:
            mock_bytes = generate_mock_portrait_images(name, count)
            return ImageGenResult(
                mock_bytes,
                prompt,
                "mock",
                res.error_note or "API 결과 없음 — 목 이미지로 대체",
            )
        except Exception as e:
            return ImageGenResult([], prompt, "mock", str(e))

    try:
        mock_bytes = generate_mock_portrait_images(name, count)
        return ImageGenResult(mock_bytes, prompt, "mock", "API 미사용 또는 키 없음 — 목 이미지")
    except Exception as e:
        return ImageGenResult([], prompt, "mock", str(e))


# ---------------------------------------------------------------------------
# 편향 분석 (규칙 + 해시 기반 시뮬레이션)
# ---------------------------------------------------------------------------


def _detect_script(name: str) -> str:
    if re.search(r"[가-힣]", name):
        return "한글 표기"
    if re.search(r"[\u0600-\u06FF]", name):
        return "아랍 문자 표기"
    if re.search(r"[\u4e00-\u9fff]", name):
        return "한자 병용/중국어권 표기 가능"
    if re.search(r"[A-Za-z]", name):
        return "라틴 문자 표기"
    return "불명확"


def analyze_bias(
    name: str,
    lang_region: str,
    image_count: int,
    prompt_strategy: str,
    second_name: str | None = None,
) -> BiasAnalysis:
    """
    이미지 대신 규칙·난수(재현적 시드)로 태깅 및 편향 점수 시뮬레이션.
    모든 문구는 '경향/가능성'으로 표현.
    """
    name = (name or "").strip() or "이름없음"
    seed = _hash_seed(name + "|" + lang_region + "|" + prompt_strategy)
    rnd = random.Random(seed)

    script = _detect_script(name)

    # 성별 관련 문구: 실제 성별을 추정하지 않고, "모델이 클리셰를 채울 수 있다"는 시뮬만 표시
    gender_guess = rnd.choice(
        [
            "생성 모델이 특정 성별 스테레오타입으로 수렴할 수 있음(시뮬, 단정 아님)",
            "성별 단서가 약해 다양한 해석이 가능(시뮬)",
            "짧은 이름·표기만으로는 불확실 — 모델이 관습적 이미지를 채울 위험(시뮬)",
            "중성적 표현을 요청하지 않으면 편향이 드러날 수 있음(시뮬)",
        ]
    )

    culture_guess = f"{lang_region} 이름 맥락 — 문화적 단서는 제한적이며 고정관념과 섞일 수 있음(시뮬)"
    if lang_region == "기타":
        culture_guess = f"언어권 불명 — {script} 기준으로만 형식적 단서(시뮬)"

    age_bucket = rnd.choice(["20대 전후로 그려질 가능성(시뮬)", "30~40대로 그려질 가능성(시뮬)", "연령 단서 약함(시뮬)"])
    style_guess = rnd.choice(["캐주얼 복장 연상(시뮬)", "비즈니스 캐주얼 연상(시뮬)", "학생 이미지 연상(시뮬)"])

    # 점수: 전략이 중립이면 전반적으로 감소
    neutral_bonus = 0.75 if prompt_strategy.startswith("중립") else 1.0
    scores = {
        "gender_bias": min(100.0, rnd.uniform(35, 85) * neutral_bonus),
        "culture_stereotype": min(100.0, rnd.uniform(30, 80) * neutral_bonus),
        "style_occupation_bias": min(100.0, rnd.uniform(25, 75) * neutral_bonus),
        "diversity_shortage": min(100.0, 40 + (4 - min(image_count, 4)) * 12 + rnd.uniform(-5, 15)),
    }

    summary_lines = [
        f"성별 표현: {gender_guess}",
        f"문화권·스타일: {culture_guess} / {style_guess}",
        f"연령 연상: {age_bucket}",
        "이름·언어권·프롬프트 조합에 따라 생성 모델이 **일관된 클리셰**를 재생산할 수 있습니다(시뮬레이션 관점).",
    ]

    if prompt_strategy.startswith("중립"):
        summary_lines.append("중립 프롬프트를 쓴 경우, 점수가 상대적으로 낮게 나오도록 시뮬레이션했습니다. 실제 API에서는 보장되지 않습니다.")

    compare_note = None
    if second_name and second_name.strip():
        seed2 = _hash_seed(second_name.strip())
        diff = abs((seed % 100) - (seed2 % 100))
        compare_note = (
            f"‘{name}’ vs ‘{second_name.strip()}’ — 시뮬레이션 지표 차이(임의): 약 {diff}p. "
            "같은 언어권·프롬프트여도 **문자열에 따라** 생성 경향이 달라질 수 있음을 가정한 데모입니다."
        )

    tags = {
        "성별 연상(시뮬)": gender_guess,
        "문화·맥락(시뮬)": culture_guess,
        "연령 연상(시뮬)": age_bucket,
        "스타일(시뮬)": style_guess,
        "표기 형식": script,
    }

    return BiasAnalysis(tags=tags, scores=scores, summary_lines=summary_lines, compare_note=compare_note)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

CARD_CSS = """
<style>
.nb-card {
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 1rem 1.1rem;
  background: linear-gradient(180deg, #fafbfc 0%, #f4f6f8 100%);
  margin-bottom: 0.6rem;
  box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
.nb-card h4 { margin: 0 0 .4rem 0; font-size: 1.05rem; color: #1e293b; }
.nb-metric { font-size: 1.6rem; font-weight: 700; color: #0f172a; }
.nb-sub { font-size: .88rem; color: #64748b; margin-top: .25rem; }
</style>
"""


def inject_css() -> None:
    st.markdown(CARD_CSS, unsafe_allow_html=True)


def bias_card(title: str, score: float, caption: str) -> None:
    st.markdown(
        f'<div class="nb-card"><h4>{title}</h4>'
        f'<div class="nb-metric">{score:.0f}</div>'
        f'<div class="nb-sub">{caption}</div></div>',
        unsafe_allow_html=True,
    )


def render_image_grid(images: list[bytes], columns: int = 2) -> None:
    if not images:
        st.warning("표시할 이미지가 없습니다.")
        return
    cols = st.columns(columns)
    for i, blob in enumerate(images):
        with cols[i % columns]:
            st.image(blob, caption=f"생성 #{i + 1}", use_container_width=True)


def main() -> None:
    st.set_page_config(
        page_title="AI 이름 편향 탐지기",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_css()

    st.title("AI 이름 편향 탐지기")
    st.caption(
        "이름 입력을 바탕으로 **생성 이미지(또는 목 이미지)**와 **편향 가능성 시뮬레이션**을 보여주는 실험용 대시보드입니다. "
        "실제 인물을 식별하거나 평가하지 않습니다."
    )

    st.warning(
        "이 결과는 AI 학습 데이터 기반의 편향을 반영할 수 있으며 **실제 인물을 의미하지 않습니다**. "
        "교육·발표 목적의 시뮬레이션입니다."
    )

    # ---- Sidebar
    with st.sidebar:
        st.header("실험 설정")
        name_a = st.text_input("이름", value="", placeholder="예: 민수, Samira Chen", key="nb_name_a")
        lang = st.selectbox("언어권", LANG_OPTIONS, index=0)
        n_img = st.slider("생성 이미지 개수", 1, 4, 2)
        mode = st.selectbox("실험 모드", EXPERIMENT_MODES)
        name_b = ""
        if mode == "이름 비교":
            name_b = st.text_input("비교 이름", value="", placeholder="비교할 다른 이름", key="nb_name_b")
        strategy = st.selectbox("프롬프트 전략", PROMPT_STRATEGIES)
        st.divider()
        use_api = st.checkbox(
            "OpenAI 이미지 API 사용 (키 있을 때)",
            value=bool(os.environ.get("OPENAI_API_KEY")),
            help="체크 해제 시 항상 목 이미지로 빠르게 동작합니다.",
        )
        st.caption("API 키: 환경변수 `OPENAI_API_KEY`")
        run = st.button("분석 시작", type="primary", use_container_width=True)

    if not run:
        st.info("사이드바에서 설정을 입력한 뒤 **분석 시작**을 눌러 주세요.")
        return

    if not name_a.strip():
        st.error("이름을 입력해 주세요.")
        return

    if mode == "이름 비교" and not (name_b or "").strip():
        st.error("이름 비교 모드에서는 비교 이름도 입력해 주세요.")
        return

    # ---- 생성
    prefer_api = use_api and bool(os.environ.get("OPENAI_API_KEY"))
    with st.spinner("이미지 생성 또는 목 이미지 준비 중…"):
        res_a = generate_images(name_a.strip(), lang, strategy, n_img, prefer_api=prefer_api)
        res_b: ImageGenResult | None = None
        if mode == "이름 비교":
            res_b = generate_images(name_b.strip(), lang, strategy, n_img, prefer_api=prefer_api)

    nb = name_b.strip() if mode == "이름 비교" else ""
    bias_a = analyze_bias(name_a.strip(), lang, n_img, strategy, second_name=nb or None)
    bias_b: BiasAnalysis | None = None
    if mode == "이름 비교":
        bias_b = analyze_bias(nb, lang, n_img, strategy, second_name=name_a.strip())

    tab_img, tab_bias, tab_help = st.tabs(["결과 이미지", "편향 분석", "해설"])

    with tab_img:
        st.subheader("생성 결과")
        st.caption(f"프롬프트 요약: `{res_a.prompt_used[:200]}…`")
        if res_a.error_note:
            st.info(f"안내: {res_a.error_note} (출처: {res_a.source})")
        else:
            st.success(f"출처: {res_a.source}")

        if mode == "단일 이름":
            render_image_grid(res_a.images, columns=2)
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### 이름 A")
                render_image_grid(res_a.images, columns=2)
            with c2:
                st.markdown("##### 이름 B")
                if res_b:
                    if res_b.error_note:
                        st.info(res_b.error_note)
                    render_image_grid(res_b.images, columns=2)

    with tab_bias:
        st.subheader("편향 분석 패널 (시뮬레이션)")
        st.caption("점수는 규칙·난수 기반 시연이며, 실제 멀티모달 모델 출력이 아닙니다.")

        def panel(bias: BiasAnalysis, label: str) -> None:
            st.markdown(f"### {label}")
            st.markdown("**추정 태그 (시뮬)**")
            for k, v in bias.tags.items():
                st.write(f"- **{k}**: {v}")
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                bias_card(
                    "성별 편향 가능성",
                    bias.scores["gender_bias"],
                    "특정 성별 클리셰로 고정될 위험(시뮬)",
                )
                bias_card(
                    "문화권 고정관념",
                    bias.scores["culture_stereotype"],
                    "특정 문화권 이미지로 수렴할 위험(시뮬)",
                )
            with c2:
                bias_card(
                    "직업·스타일 편향",
                    bias.scores["style_occupation_bias"],
                    "복장·직업 연상이 편향될 위험(시뮬)",
                )
                bias_card(
                    "다양성 부족",
                    bias.scores["diversity_shortage"],
                    "적은 샘플일수록 단일 패턴에 머물 수 있음(시뮬)",
                )
            for line in bias.summary_lines:
                st.write(line)
            if bias.compare_note:
                st.info(bias.compare_note)

        panel(bias_a, "이름 A")
        if bias_b:
            st.divider()
            panel(bias_b, "이름 B")

    with tab_help:
        st.subheader("왜 이런 현상이 논의되나요?")
        with st.expander("AI 편향이 발생하는 이유", expanded=True):
            st.markdown(
                """
                - 학습 데이터에 **특정 이름·문화·성별**과 결합된 이미지가 불균형하게 존재할 수 있습니다.
                - 텍스트-이미지 모델은 이름을 **언어적 단서**로 취해 자주 등장한 연상을 재생산합니다.
                - 사용자 프롬프트가 짧을수록 모델이 **빈칸을 클리셰로 채울** 여지가 커집니다.
                """
            )
        with st.expander("데이터 기반 학습의 한계"):
            st.markdown(
                """
                - 데이터는 **과거의 세계**를 반영하며, 공정성이나 대표성을 보장하지 않습니다.
                - 필터링·정책이 없으면 **고정관념이 시각적으로 강화**될 수 있습니다.
                """
            )
        with st.expander("이름 → 이미지 연결의 위험성"):
            st.markdown(
                """
                - 이름만으로 사람의 외모·정체성을 추론하는 것은 **부적절**하며 본 앱은 이를 **비판적으로 보여주기 위한 실험**입니다.
                - 실제 서비스에서는 수집 최소화·목적 제한·설명 가능성·거절권 등이 필요합니다.
                """
            )

    st.divider()
    st.caption("© 교육용 데모 · OpenAI API 미사용 시 목 이미지로 동작합니다.")


if __name__ == "__main__":
    main()
