# -*- coding: utf-8 -*-
"""
app/service/logo/make_logo_illustration.py

축제 일러스트 로고(정사각형 2048x2048)용
Seedream 입력/프롬프트 생성 + 생성 이미지 저장 + editor 저장 모듈.

역할
- 참고용 포스터 이미지(URL 또는 로컬 파일 경로)와 축제 정보(한글)를 입력받아서
  1) 한글 축제명에서 '제 N회' 같은 회차 표현을 제거하고
  2) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  3) 영어 축제명에서 연도/숫자/회차를 제거한 "축제 이름"만 남긴다.
     (예: "2025 Boryeong Mud Festival" -> "Boryeong Mud Festival")
  4) 포스터 색감/무드/키워드를 분석해서, 락/우주/머드/빛/겨울 등 테마를 추정한다.
  5) 테마에 맞는 심벌(기타, 해골, 로켓, 물결, 눈꽃 등)을 포함한
     배지형/엠블럼형 로고 프롬프트를 조립한다. (write_logo_illustration)
  6) 해당 JSON을 Replicate(Seedream)에 넘겨 실제 일러스트 로고 이미지를 생성하고 저장한다. (create_logo_illustration)
  7) run_logo_illustration_to_editor(...) 로 run_id 기준 editor 폴더에 JSON/이미지 사본을 저장한다.
  8) python make_logo_illustration.py 로 단독 실행할 수 있다.

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
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

import replicate
from dotenv import load_dotenv
from replicate.exceptions import ModelError

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
    _build_scene_phrase_from_poster,
    _extract_poster_url_from_input,
    _save_image_from_file_output,
    _download_image_bytes,
)


# -------------------------------------------------------------
# 회차 제거: "제 15회 ○○축제" → "○○축제"
# -------------------------------------------------------------
def _strip_edition_from_name_ko(name: str) -> str:
    """축제명에서 '제 15회', '15회' 같은 회차 표현을 제거."""
    if not name:
        return ""
    s = str(name)
    s = re.sub(r"^\s*제\s*\d+\s*회\s*", "", s)
    s = re.sub(r"^\s*\d+\s*회\s*", "", s)
    return s.strip()


# -------------------------------------------------------------
# 영어 축제명에서 연도/숫자/서수 제거
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
# 영어 정보에서 테마 추론 (rock, mud, light, space, winter 등)
# -------------------------------------------------------------
def _infer_theme_from_english(
    name_en: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    """
    영어 축제명 + 씬 묘사를 바탕으로 대략적인 테마 문자열을 만든다.
    - rock / music
    - mud
    - light / illumination
    - space / aerospace
    - snow / ice / winter
    - fireworks
    - default: generic festival
    """
    text = f"{name_en} {base_scene_en} {details_phrase_en}".lower()

    if "rock" in text:
        return "rock music festival"
    if "jazz" in text or "band" in text or "concert" in text:
        return "music festival"
    if "mud" in text or "clay" in text:
        return "mud festival"
    if "light" in text or "illumination" in text or "lantern" in text or "neon" in text:
        return "light festival"
    if (
        "aerospace" in text
        or "space" in text
        or "cosmic" in text
        or "galaxy" in text
        or "star" in text
    ):
        return "space festival"
    if "snow" in text or "ice" in text or "winter" in text or "frost" in text:
        return "winter festival"
    if "firework" in text or "pyro" in text:
        return "fireworks festival"

    return "festival logo"


# -------------------------------------------------------------
# 1) 일러스트 로고 프롬프트 (테마 기반 심벌 + 영문 축제명)
# -------------------------------------------------------------
def _build_logo_illustration_prompt_en(
    festival_name_en: str,
    festival_theme_en: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    """
    축제 영문 타이틀 + 테마 심벌 조합 로고용 Seedream 프롬프트.

    - 중앙/상단에는 테마를 강하게 드러내는 추상/심볼형 아이콘
    - 그 아래 또는 오른쪽에는 영문 축제명 1~3줄
    - 배경은 흰색 또는 매우 밝은 단색
    - 숫자(연도, 회차), 한글, 슬로건은 절대 넣지 않음
    """

    def _n(s: str) -> str:
        return " ".join(str(s or "").split())

    festival_name_en = _n(festival_name_en)
    festival_theme_en = _n(festival_theme_en)
    base_scene_en = _n(base_scene_en)
    details_phrase_en = _n(details_phrase_en)

    prompt = f"""
Clean, modern festival logo in flat vector style.
Use a pure white or very light solid background with absolutely NO texture,
NO paper mockup, NO 3D foil or embossing.

###
THEME-BASED SYMBOL
Create a bold abstract symbol that strongly reflects the festival theme: "{festival_theme_en}".
The symbol MUST be clear, iconic, and built from simple geometric shapes.

ROCK / MUSIC FESTIVAL EXAMPLES:
- electric guitars (single or crossed)
- clean vector skull (no gore)
- microphones
- speakers / amps
- thunder bolts / energy shapes
- drumsticks or drums
- vinyl record icon
- rock hand sign with two raised fingers
- wings, banners, shields, stars

LIGHT FESTIVAL EXAMPLES:
- glowing arcs or beams
- starbursts
- simplified lantern shapes
- neon line geometry

MUD FESTIVAL EXAMPLES:
- dynamic splash and blob shapes
- round emblems with mud-like silhouettes (vector only)

SPACE / AEROSPACE FESTIVAL EXAMPLES:
- rockets
- planets
- orbit rings
- minimal satellite-like shapes
- abstract constellations

WINTER / SNOW FESTIVAL EXAMPLES:
- snowflakes
- icy shards
- frosty circles

The symbol must be stylised, minimal, and logo-like,
not a detailed illustration or scene.

###
LAYOUT VARIATIONS
The overall logo layout CAN be:
- a circular badge with the symbol in the centre,
- an oval or shield emblem,
- a top–bottom stacked layout (symbol on top, text below),
- a left symbol + right text layout,
- or a symbol inside a circle with the festival name arranged around the rim.

Choose whichever layout creates the strongest logo composition.

###
TEXT RULES
Below or beside the symbol, place the exact English festival name:
"{festival_name_en}"

You MUST copy this title string EXACTLY, character by character.
- Do NOT change, remove, shorten, abbreviate, or repeat any word.
- Do NOT invent extra words like "Fes", "Fest", "Event", or add another "Festival".
- Do NOT translate, paraphrase, or re-order any words.
- The ONLY allowed modification is inserting line breaks between the existing words.

You may break the title into one, two, or three lines,
but you must preserve the original order and spelling of all words
in "{festival_name_en}" with no additions or deletions.

Use a strong, legible typeface (modern sans-serif or refined serif).
Keep the text crisp, vector-like, and not overly decorative.

The ONLY text allowed in the entire image is the festival name "{festival_name_en}".
Do NOT add any years, numbers, edition counts, dates, slogans, or taglines.
Do NOT add Korean text or any non-Latin scripts.
Do NOT add URLs, hashtags, labels like "ESTD", "2024", "FES" or "FEST".

###
STYLE RULES
- Pure vector look with sharp edges and strong shapes.
- Use a limited colour palette inspired by the attached poster image:
  base your colours on the mood and palette suggested by {base_scene_en} and {details_phrase_en}.
- You may use subtle gradients inside the symbol or text,
  but the background must stay solid and flat.
- NO texture, halftone, grain, or realistic lighting.

###
FORBIDDEN
- Do NOT copy the exact composition or objects from the poster.
- Do NOT draw complex scenes, characters, full instruments in detail, or landscapes.
- Do NOT add watermarks, UI elements, or app icons.
- Do NOT add shadows under the canvas or 3D extrusions.

###
FINAL GOAL
Produce a bold, thematic festival logo that feels ready for branding:
a strong central symbol that clearly reflects the theme,
plus the English festival name integrated cleanly below or beside it.
Do not draw quotation marks.
"""
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

    - festival_name_ko 에 '제 7회', '제 15회' 등이 포함되어 있어도
      회차를 제거한 순수 축제명만 번역에 사용한다.
    - 번역된 영어 축제명에서 연도/숫자를 제거한 "축제 이름"만 남긴다.
    - 포스터 색감/무드/키워드를 이용해 대략적인 축제 테마 문자열을 만든다.
    - 이미지에는 이 영문 축제명만 텍스트로 사용하도록 프롬프트를 구성한다.
    """

    # 0) 회차 제거된 순수 축제명
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

    # 1-1) 영어 축제명에서 연도/숫자/서수 제거
    name_en = _strip_numbers_from_english_name(name_en_raw)

    if not name_en:
        raise ValueError(
            f"영어 축제명이 비어 있어 일러스트 로고를 생성할 수 없습니다. (원본: {name_en_raw!r})"
        )

    # 2) 포스터 이미지 분석 → 색감/무드/키워드 정리
    scene_info = _build_scene_phrase_from_poster(
        poster_image_url=poster_image_url,
        festival_name_en=name_en,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )
    base_scene_en = scene_info["base_scene_en"]
    details_phrase_en = scene_info["details_phrase_en"]

    # 3) 영어 정보 + 씬 묘사 → 테마 추론
    festival_theme_en = _infer_theme_from_english(
        name_en=name_en,
        base_scene_en=base_scene_en,
        details_phrase_en=details_phrase_en,
    )

    # 4) 최종 프롬프트 조립
    prompt = _build_logo_illustration_prompt_en(
        festival_name_en=name_en,
        festival_theme_en=festival_theme_en,
        base_scene_en=base_scene_en,
        details_phrase_en=details_phrase_en,
    )

    # 5) Seedream / Replicate 입력 JSON 구성
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": LOGO_ILLUST_WIDTH_PX,
        "height": LOGO_ILLUST_HEIGHT_PX,
        "prompt": prompt,
        "max_images": 1,
        "aspect_ratio": "match_input_image",
        "enhance_prompt": True,
        "sequential_image_generation": "disabled",
        "image_input": [
            {
                "type": "image_url",
                "url": poster_image_url,
            }
        ],
        # 결과 조립용 메타데이터
        "festival_name_en": name_en,
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
    1) image_input 에서 포스터 URL/경로를 추출하고,
    2) 그 이미지를 다운로드(또는 로컬 파일 읽기)해 파일 객체로 만든 뒤,
    3) Replicate(bytedance/seedream-4 또는 LOGO_ILLUSTRATION_MODEL)에
       prompt + image_input과 함께 전달해
       실제 2048x2048 일러스트 로고 이미지를 생성하고,
    4) 생성된 이미지를 로컬에 저장한다.
    """

    poster_url = _extract_poster_url_from_input(seedream_input)
    if not poster_url:
        raise ValueError(
            "seedream_input.image_input 에 참조 포스터 이미지 URL/경로가 없습니다."
        )

    img_bytes = _download_image_bytes(poster_url)
    image_file = BytesIO(img_bytes)

    prompt = seedream_input.get("prompt", "")
    size = seedream_input.get("size", "custom")
    width = int(seedream_input.get("width", LOGO_ILLUST_WIDTH_PX))
    height = int(seedream_input.get("height", LOGO_ILLUST_HEIGHT_PX))
    max_images = int(seedream_input.get("max_images", 1))
    aspect_ratio = seedream_input.get("aspect_ratio", "match_input_image")
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
        "image_input": [image_file],
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
    run_id = 5

    poster_image_url = r"C:\final_project\ACC\acc-ai\app\data\banner\arco.png"
    festival_name_ko = "예술 인형 축제"
    festival_period_ko = "2025.11.04 ~ 2025.11.09"
    festival_location_ko = "아르코꿈밭극장, 텃밭스튜디오"

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
