# -*- coding: utf-8 -*-
"""
app/service/logo/make_logo_illustration.py

축제 일러스트 로고(정사각형 2048x2048)용
Seedream 입력/프롬프트 생성 + 생성 이미지 저장 + editor 저장 모듈.

역할
- 참고용 포스터 이미지 경로 + 축제 정보(한글)를 입력받아서
  1) 한글 축제명에서 '제 N회' 같은 회차 표현을 제거하고
  2) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  3) 텍스트는 연도/회차를 제거한 영어 축제명 그대로여야 하고, 일러스트와 시각적으로 하나의 로고처럼 어우러져야 한다.
  4) 축제명(한/영) + 기간 + 장소 텍스트와 포스터 이미지를 LLM에 전달해서
     축제 테마와 시각적 모티프를 요약한 영어 문장(festival_theme_en)을 만든다.
  5) festival_theme_en을 기반으로,
     "단색 배경 + 중앙의 단순 일러스트 + 연도/회차를 제거한 영어 축제명 텍스트" 조합의
     로고 프롬프트를 조립한다. (write_logo_illustration)
  6) 해당 JSON을 Replicate(Seedream)에 넘겨 (image_input 없이)
     실제 일러스트 로고 이미지를 생성하고 저장한다. (create_logo_illustration)
  7) run_logo_illustration_to_editor(...) 로 run_id 기준 editor 폴더에 JSON/이미지 사본을 저장한다.
  8) python make_logo_illustration.py 로 단독 실행할 수 있다.


디자인 제약 (반드시 지켜야 할 규칙)
1. 배경은 단색(ONE solid color)이어야 한다. 그라디언트/패턴/질감/테두리 금지.
2. 중앙에 축제와 관련된 "단순한 일러스트"와 "텍스트"가 합쳐진 하나의 로고 마크가 있어야 한다.
3. 텍스트는 연도/회차를 제거한 영어 축제명 그대로여야 하고, 일러스트와 시각적으로 하나의 로고처럼 어우러져야 한다.
4. 배경 + (중앙 일러스트 + 텍스트) 외에는 어떤 요소도 추가하면 안 된다.
   (추가 아이콘, 장식선, 배지, 그림, 부가 텍스트, 워터마크 등 모두 금지)

결과 JSON 예시:

{
  "type": "logo_illustration",
  "pro_name": "일러스트 로고",
  "festival_name_en": "Boryeong Mud Festival",
  "width": 2048,
  "height": 2048,
  "image_url": "http://localhost:5000/static/editor/11/before_image/logo_illustration_....png"
}

전제 환경변수
- OPENAI_API_KEY                  : OpenAI API 키
- BANNER_LLM_MODEL                : (선택) 배너/버스/로고용 LLM, 기본값 "gpt-4o-mini"
- LOGO_ILLUSTRATION_MODEL         : (선택) 기본값 "bytedance/seedream-4"
- LOGO_ILLUSTRATION_SAVE_DIR      : (선택) 직접 create_logo_illustration 를 쓸 때 저장 경로
- ACC_AI_BASE_URL                 : (선택) 이미지 전체 URL 앞부분, 기본값 "http://localhost:5000"
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import replicate
from dotenv import load_dotenv
from replicate.exceptions import ModelError
from openai import OpenAI

# -------------------------------------------------------------
# 프로젝트 루트 및 .env 로딩 + sys.path 설정
# -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / "app" / "data"

LOGO_ILLUST_TYPE = "logo_illustration"
LOGO_ILLUST_PRO_NAME = "일러스트 로고"
LOGO_ILLUST_WIDTH_PX = 2048
LOGO_ILLUST_HEIGHT_PX = 2048

env_path = PROJECT_ROOT / ".env"
load_dotenv(env_path)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# road_banner 공용 유틸 재사용
from app.service.banner_khs.make_road_banner import (  # type: ignore
    _translate_festival_ko_to_en,
    _build_scene_phrase_from_poster,   # ✅ 포스터 분석 함수 추가
    _save_image_from_file_output,
)

# -------------------- OpenAI 클라이언트 --------------------
_client: Optional[OpenAI] = None


def _get_openai_client() -> OpenAI:
    """OPENAI_API_KEY를 사용하는 전역 OpenAI 클라이언트 (한 번만 생성)."""
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


# -------------------------------------------------------------
# 회차 제거: "제 15회 ○○축제" → "○○축제"
# -------------------------------------------------------------
def _strip_edition_from_name_ko(name: str) -> str:
    """축제명에서 '제 15회', '15회', 앞에 붙은 연도(2025 등) 같은 회차/연도 표현을 제거."""
    if not name:
        return ""
    s = str(name)

    # 앞에 붙은 연도 (예: "2024 안동국제 탈춤 페스티벌")
    s = re.sub(r"^\s*\d{4}\s*년?\s*", "", s)

    # "제 15회", "제15회" 패턴 제거
    s = re.sub(r"^\s*제\s*\d+\s*회\s*", "", s)

    # "15회 ○○축제" 패턴 제거
    s = re.sub(r"^\s*\d+\s*회\s*", "", s)

    return s.strip()


# -------------------------------------------------------------
# 영어 축제명에서 연도/숫자/서수 제거 (테마 추론용 + 텍스트용)
# -------------------------------------------------------------
def _strip_numbers_from_english_name(name_en: str) -> str:
    """
    영어 축제명에서 연도/숫자/순서 표현을 제거한다.

    예:
      "2025 Boryeong Mud Festival"      -> "Boryeong Mud Festival"
      "25th Jinju Lantern Festival"     -> "Jinju Lantern Festival"
      "14th Daegu Flower Festival 2024" -> "Daegu Flower Festival"
    """
    if not name_en:
        return ""

    s = str(name_en)

    # "25th", "3rd", "2nd", "1st" 등 제거
    s = re.sub(r"\b\d+(st|nd|rd|th)\b", "", s, flags=re.IGNORECASE)

    # 순수 숫자 토큰 (연도 등) 제거
    s = re.sub(r"\b\d{2,4}\b", "", s)

    # 공백 정리
    s = " ".join(s.split())
    return s


# -------------------------------------------------------------
# 축제 정보(텍스트)에서 테마 문장 추론 (LLM)
# -------------------------------------------------------------
def _infer_theme_from_english(
    festival_name_ko: str,
    festival_name_en_for_theme: str,
    festival_period_en: str,
    festival_location_en: str,
) -> str:
    """
    축제명(한/영) + 기간 + 장소 텍스트를 바탕으로,
    로고용 시각 테마를 한 줄 영어 문장으로 요약한다.

    - 예: "space rockets, launch pad, deep blue night sky, stars"
    - 예: "colorful lanterns, glowing lights, warm evening streets"
    """
    client = _get_openai_client()
    model = os.getenv("BANNER_LLM_MODEL", "gpt-4o-mini")

    def _n(s: str) -> str:
        return " ".join(str(s or "").split())

    festival_name_ko = _n(festival_name_ko)
    festival_name_en_for_theme = _n(festival_name_en_for_theme)
    festival_period_en = _n(festival_period_en)
    festival_location_en = _n(festival_location_en)

    system_msg = (
        "You write very short English descriptions of visual themes for logos. "
        "Given information about a festival, you must extract the underlying visual theme "
        "and main symbolic motifs. Use only concepts that are clearly implied by the input. "
        "Your output will be used as a hint for an image generation model."
    )

    user_msg = (
        "We are going to design a simple illustration-style logo with an icon and an English title.\n\n"
        f"Korean festival name: {festival_name_ko}\n"
        f"English festival name (no numbers): {festival_name_en_for_theme}\n"
        f"Festival period (EN): {festival_period_en}\n"
        f"Festival location (EN): {festival_location_en}\n\n"
        "From this information, write ONE short English phrase (max 12 words) that describes the visual theme "
        "and key symbolic motifs. Focus on objects, environments, and abstract motifs that would make sense as "
        "a simple illustration.\n\n"
        "Rules:\n"
        "- Use only ideas that are clearly suggested by the names, period, or location.\n"
        "- Do NOT invent random unrelated themes.\n"
        '- Do NOT include years, dates, place names, or the word \"festival\".\n'
        "Return only the phrase, nothing else."
    )

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
    )

    # responses.create 결과에서 순수 텍스트만 추출 (gpt-4o-mini 기준)
    try:
        theme_text = resp.output[0].content[0].text  # type: ignore[attr-defined]
    except Exception as e:  # pragma: no cover - 방어적 코드
        raise RuntimeError(f"축제 테마 LLM 응답 파싱 실패: {e!r} / raw={resp!r}")

    theme_text = " ".join(str(theme_text or "").strip().split())
    if not theme_text:
        raise RuntimeError("축제 테마 문장을 LLM에서 비어 있게 반환했습니다.")

    return theme_text


# -------------------------------------------------------------
# 1) 일러스트 로고 프롬프트
#    - 단색 배경
#    - 중앙의 "단순 일러스트 + 영어 축제명" 하나만 존재
# -------------------------------------------------------------
def _build_logo_illustration_prompt_en(
    festival_full_name_en: str,
    festival_theme_en: str,
) -> str:
    def _n(s: str) -> str:
        return " ".join(str(s or "").split())

    festival_full_name_en = _n(festival_full_name_en)
    festival_theme_en = _n(festival_theme_en)

    prompt = (
        # 상단: 전체 규칙 요약 (1)~(5)
        "Square 1:1 festival illustration logo. "
        "Follow these exact visual rules: "
        "1) The background must be a single solid flat color. "
        "2) In the center, place one compact combined logo made only of a simple illustration and the full English festival title. "
        "3) Design the illustration to clearly reflect the festival theme described in the text. "
        "4) Make the festival title text visually integrated with the illustration so they look like one unified logo mark. "
        "5) Other than the solid background and this single central illustration+text logo, do not draw anything else at all. "

        # 배경: 완전 단색
        "Fill the entire canvas with exactly one flat background color, from edge to edge. "
        "Do not use gradients, textures, patterns, noise, borders, vignettes, frames, photographs, or images in the background. "

        # 중앙 로고: 단순 일러스트 + 영어 축제명
        f"The central logo must be a very simple flat illustration combined with text. "
        f"The illustration should be a clean minimal symbol that represents this festival theme: \"{festival_theme_en}\". "
        "Use a minimal, vector-like style with clean geometric shapes and avoid complex scenery or multiple scattered elements. "
        f"The text must show the full English festival title exactly as follows: \"{festival_full_name_en}\". "
        "Arrange the illustration and the text so they clearly belong together as a single compact logo in the centre of the canvas, "
        "with generous empty margin around them. The text must remain easy to read from a distance. "

        # 텍스트 규칙
        "Use the festival title exactly as provided. Do not translate, shorten, or change any words. "
        "Do not add any extra text such as dates, locations, slogans, URLs, hashtags, or tags. "
        "Use only Latin letters from the title; do not use Korean or any other scripts. "

        # 스타일 제한
        "Keep the illustration and text in a simple flat style. "
        "Do not use 3D effects, inner or outer glows, gradients, heavy shadows, glossy highlights, or realistic rendering. "

        # 절대 추가 금지 요소들
        "Do NOT add other icons, pictograms, characters, landscapes, decorative shapes, lines, frames, badges, or logos anywhere. "
        "Do NOT place extra graphics or text in the corners or along the edges. "
        "The final image must contain only: one solid background colour and one central combined illustration plus the full English festival title. "
        "Do not draw quotation marks."
    )

    return prompt.strip()


# -------------------------------------------------------------
# 2) write_logo_illustration: Seedream 입력 JSON 생성
# -------------------------------------------------------------
def write_logo_illustration(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    축제 일러스트 로고(2048x2048)용 Seedream 입력 JSON 생성.

    - poster_image_url 은 참고용 포스터 이미지 경로(또는 URL)이다.
      이미지는 Seedream image_input 으로 직접 사용하지 않고 LLM 분석용으로만 활용한다.
    - festival_name_ko 에 '제 7회', '제 15회', '2025년' 등이 포함되어 있어도
      회차/연도를 제거한 순수 축제명만 번역에 사용한다.
    - 최종 텍스트는 연도/숫자/회차를 제거한 영어 축제명만 사용한다.
    - 축제명(한/영) + 기간 + 장소 + 포스터 이미지를 이용해
      LLM으로 대략적인 축제 테마 문장(festival_theme_en)을 만든다.
    - 이미지에는 이 "영문 축제명(연도/회차 제거)"만 텍스트로 사용하도록 프롬프트를 구성한다.
    """

    # 0) 회차/연도 제거된 순수 한글 축제명
    festival_name_ko_clean = _strip_edition_from_name_ko(festival_name_ko)

    # 1) 한글 축제 정보 → 영어 번역
    translated = _translate_festival_ko_to_en(
        festival_name_ko=festival_name_ko_clean,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )
    name_en_raw = translated.get("name_en", "")
    period_en = translated.get("period_en", "")
    location_en = translated.get("location_en", "")

    if not name_en_raw:
        raise ValueError(
            f"영어 축제명이 비어 있어 일러스트 로고를 생성할 수 없습니다. (원본: {name_en_raw!r})"
        )

    # 1-1) 테마 추론용: 연도/숫자/서수 제거한 버전
    name_en_for_theme = _strip_numbers_from_english_name(name_en_raw) or name_en_raw

    # 1-2) 최종 텍스트용: 연도/숫자/서수를 제거한 순수 축제명
    festival_full_name_en = _strip_numbers_from_english_name(name_en_raw) or " ".join(
        str(name_en_raw).split()
    )

    # 2) 텍스트 기반 테마 문장 추론 (LLM)
    theme_from_text = _infer_theme_from_english(
        festival_name_ko=festival_name_ko_clean,
        festival_name_en_for_theme=name_en_for_theme,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )

    # 2-1) 포스터 기반 씬/색감/무드 분석 (LLM vision) – 타이포그래피 로고와 동일한 방식
    scene_info = _build_scene_phrase_from_poster(
        poster_image_url=poster_image_url,
        festival_name_en=festival_full_name_en,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )
    base_scene_en = str(scene_info.get("base_scene_en", ""))
    details_phrase_en = str(scene_info.get("details_phrase_en", ""))

    # 2-2) 텍스트 테마 + 포스터 테마를 하나의 문장으로 합치기
    combined_theme_parts = [
        theme_from_text,
        base_scene_en,
        details_phrase_en,
    ]
    combined_theme = " ".join(
        " ".join(part for part in combined_theme_parts if part).split()
    )
    festival_theme_en = combined_theme or theme_from_text or base_scene_en or details_phrase_en

    # 3) 최종 프롬프트 조립
    prompt = _build_logo_illustration_prompt_en(
        festival_full_name_en=festival_full_name_en,
        festival_theme_en=festival_theme_en,
    )

    # 4) Seedream / Replicate 입력 JSON 구성 (image_input 없이)
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": LOGO_ILLUST_WIDTH_PX,
        "height": LOGO_ILLUST_HEIGHT_PX,
        "prompt": prompt,
        "max_images": 1,
        "aspect_ratio": "1:1",
        "enhance_prompt": True,
        "sequential_image_generation": "disabled",
        # 결과 조립용 메타데이터
        "festival_name_en": festival_full_name_en,
        "festival_theme_en": festival_theme_en,
        "festival_base_name_ko": str(festival_name_ko or ""),
        "festival_base_name_ko_clean": str(festival_name_ko_clean or ""),
        "festival_base_period_ko": str(festival_period_ko or ""),
        "festival_base_location_ko": str(festival_location_ko or ""),
    }

    return seedream_input


# -------------------------------------------------------------
# 3) 저장 디렉터리
# -------------------------------------------------------------
def _get_logo_illustration_save_dir() -> Path:
    """
    LOGO_ILLUSTRATION_SAVE_DIR 환경변수가 있으면:
      - 절대경로면 그대로 사용
      - 상대경로면 PROJECT_ROOT 기준으로 사용
    없으면:
      - PROJECT_ROOT/app/data/logo_illustration 사용
    """
    env_dir = os.getenv("LOGO_ILLUSTRATION_SAVE_DIR")
    if env_dir:
        p = Path(env_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    return DATA_ROOT / "logo_illustration"


# -------------------------------------------------------------
# 4) create_logo_illustration: Seedream 호출 + 저장
# -------------------------------------------------------------
def create_logo_illustration(
    seedream_input: Dict[str, Any],
    save_dir: Path | None = None,
    prefix: str = "logo_illustration_",
) -> Dict[str, Any]:
    """
    write_logo_illustration(...) 에서 만든 Seedream 입력 JSON을 그대로 받아
    1) 프롬프트/사이즈 정보를 읽고,
    2) Replicate(bytedance/seedream-4 또는 LOGO_ILLUSTRATION_MODEL)에
       prompt만 전달해 (image_input 없이) 실제 2048x2048 일러스트 로고 이미지를 생성하고,
    3) 생성된 이미지를 로컬에 저장한다.
    """

    prompt = str(seedream_input.get("prompt", ""))
    size = seedream_input.get("size", "custom")
    width = int(seedream_input.get("width", LOGO_ILLUST_WIDTH_PX))
    height = int(seedream_input.get("height", LOGO_ILLUST_HEIGHT_PX))
    max_images = int(seedream_input.get("max_images", 1))
    aspect_ratio = seedream_input.get("aspect_ratio", "1:1")
    enhance_prompt = bool(seedream_input.get("enhance_prompt", True))
    sequential_image_generation = seedream_input.get(
        "sequential_image_generation", "disabled"
    )

    replicate_input = {
        "size": size,
        "width": width,
        "height": height,
        "prompt": prompt,
        "max_images": max_images,
        "aspect_ratio": aspect_ratio,
        "enhance_prompt": enhance_prompt,
        "sequential_image_generation": sequential_image_generation,
    }

    model_name = os.getenv("LOGO_ILLUSTRATION_MODEL", "bytedance/seedream-4")

    output = None
    last_err: Exception | None = None

    for attempt in range(3):
        try:
            output = replicate.run(model_name, input=replicate_input)
            break
        except ModelError as e:
            msg = str(e)
            if "Prediction interrupted" in msg or "code: PA" in msg:
                last_err = e
                time.sleep(1.0)
                continue
            raise RuntimeError(
                f"Seedream model error during illustration logo generation: {e}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error during illustration logo generation: {e}"
            )

    if output is None:
        raise RuntimeError(
            f"Seedream model error during illustration logo generation after retries: {last_err}"
        )

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]

    if save_dir is not None:
        save_base = Path(save_dir)
    else:
        save_base = _get_logo_illustration_save_dir()
    save_base.mkdir(parents=True, exist_ok=True)

    image_path, image_filename = _save_image_from_file_output(
        file_output, save_base, prefix=prefix
    )

    return {
        "size": size,
        "width": width,
        "height": height,
        "image_path": image_path,
        "image_filename": image_filename,
        "prompt": prompt,
        "festival_name_en": str(seedream_input.get("festival_name_en", "")),
        "festival_theme_en": str(seedream_input.get("festival_theme_en", "")),
    }


# -------------------------------------------------------------
# 5) editor 저장용 헬퍼
# -------------------------------------------------------------
def run_logo_illustration_to_editor(
    run_id: int,
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    입력:
        run_id
        poster_image_url
        festival_name_ko
        festival_period_ko
        festival_location_ko

    동작:
      1) write_logo_illustration(...) 로 Seedream 입력용 seedream_input 생성
      2) create_logo_illustration(..., save_dir=before_image_dir) 로
         실제 일러스트 로고 이미지를 생성하고,
         app/data/editor/<run_id>/before_image/logo_illustration_*.png 로 저장한다.
      3) 타입, 영문 축제명, 픽셀 단위 가로/세로, static 전체 URL을 포함한
         최소 결과 JSON을 구성하여
         app/data/editor/<run_id>/before_data/logo_illustration.json 에 저장한다.
    """

    seedream_input = write_logo_illustration(
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    editor_root = DATA_ROOT / "editor" / str(run_id)
    before_data_dir = editor_root / "before_data"
    before_image_dir = editor_root / "before_image"
    before_data_dir.mkdir(parents=True, exist_ok=True)
    before_image_dir.mkdir(parents=True, exist_ok=True)

    create_result = create_logo_illustration(
        seedream_input,
        save_dir=before_image_dir,
        prefix="logo_illustration_",
    )

    image_filename = create_result["image_filename"]

    base_url = os.getenv("ACC_AI_BASE_URL", "http://localhost:5000").rstrip("/")
    static_prefix = "/static"
    image_url = f"{base_url}{static_prefix}/editor/{run_id}/before_image/{image_filename}"

    # 🔽 여기에서 poster_image_url 필드만 제거
    result: Dict[str, Any] = {
        "type": LOGO_ILLUST_TYPE,
        "pro_name": LOGO_ILLUST_PRO_NAME,
        "festival_name_en": create_result["festival_name_en"],
        "width": LOGO_ILLUST_WIDTH_PX,
        "height": LOGO_ILLUST_HEIGHT_PX,
        "image_url": image_url,
    }

    json_path = before_data_dir / "logo_illustration.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


# -------------------------------------------------------------
# 6) CLI main
# -------------------------------------------------------------
def main() -> None:
    """
    python app/service/logo/make_logo_illustration.py
    """

    # 1) 여기 값만 네가 원하는 걸로 수정해서 쓰면 됨
    run_id = 10

    poster_image_url = r"C:\final_project\ACC\acc-ai\app\data\banner\geoje.png"
    festival_name_ko = "거제몽돌해변축제"
    festival_period_ko = "2013.07.13 ~ 2013.07.14"
    festival_location_ko = "학동흑진주몽돌해변"

    # 2) 필수값 체크
    missing = []
    if not poster_image_url:
        missing.append("poster_image_url")
    if not festival_name_ko:
        missing.append("festival_name_ko")
    if not festival_period_ko:
        missing.append("festival_period_ko")
    if not festival_location_ko:
        missing.append("festival_location_ko")

    if missing:
        print("⚠️ main() 안에 아래 값들을 채워주세요:")
        for k in missing:
            print("  -", k)
        return

    # 3) 실제 실행
    result = run_logo_illustration_to_editor(
        run_id=run_id,
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    editor_root = DATA_ROOT / "editor" / str(run_id)
    json_path = editor_root / "before_data" / "logo_illustration.json"
    image_dir = editor_root / "before_image"

    print("✅ illustration logo 생성 + editor 저장 완료")
    print("  type             :", result.get("type"))
    print("  pro_name         :", result.get("pro_name"))
    print("  festival_name_en :", result.get("festival_name_en"))
    print("  width x height   :", result.get("width"), "x", result.get("height"))
    print("  image_url        :", result.get("image_url"))
    print("  json_path        :", json_path)
    print("  image_dir        :", image_dir)


if __name__ == "__main__":
    main()
