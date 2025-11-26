# -*- coding: utf-8 -*-
"""
app/service/logo/make_logo_typography.py

축제 알파벳 타이포그래피 로고(정사각형 2048x2048)용
Seedream 입력/프롬프트 생성 + 생성 이미지 저장 + editor 저장 모듈.

역할
- 참고용 포스터 이미지(URL 또는 로컬 파일 경로)와 축제 정보(한글)를 입력받아서
  1) 한글 축제명에서 '제 N회' 같은 회차 표현을 제거하고
  2) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  3) 영어 축제명(예: Goheung Aerospace Festival)을 기준으로
     3~5자의 대문자 모노그램 텍스트를 만든다. (예: GAF, DGF 등)
  4) 포스터 이미지를 시각적으로 분석해서 색감/무드/키워드를 영어로 정리한 뒤
  5) "큰 모노그램 알파벳 + 아래 작은 영어 풀 네임 한 줄" 구조의
     타이포그래피 로고 프롬프트를 조립한다. (write_logo_typography)
  6) 해당 JSON을 받아 Replicate(Seedream)를 호출해 실제 타이포 로고 이미지를 생성하고 저장한다. (create_logo_typography)
  7) run_logo_typography_to_editor(...) 로 run_id 기준 editor 폴더에 JSON/이미지 사본을 저장한다.
  8) python make_logo_typography.py 로 단독 실행할 수 있다.

※ 로고 이미지 안에 들어가는 텍스트 규칙
- 메인: 모노그램 알파벳 (예: GAF, BMF)
- 서브: 영어 축제명에서 연도/숫자/회차를 제거한 "축제 이름"만
  예) "2025 Boryeong Mud Festival" -> "Boryeong Mud Festival"
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

import replicate
from dotenv import load_dotenv
from replicate.exceptions import ModelError

# -------------------------------------------------------------
# 프로젝트 루트 및 .env 로딩 + sys.path 설정
# -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / "app" / "data"

LOGO_TYPO_TYPE = "logo"
LOGO_TYPO_PRO_NAME = "로고"
LOGO_TYPO_WIDTH_PX = 2048
LOGO_TYPO_HEIGHT_PX = 2048

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
# 영어 축제명에서 연도/숫자/순서 제거
# -------------------------------------------------------------
def _strip_numbers_from_english_name(name_en: str) -> str:
    """
    영어 축제명에서 연도/숫자/순서 표현을 제거한다.

    예:
      "2025 Boryeong Mud Festival" -> "Boryeong Mud Festival"
      "25th Jinju Lantern Festival" -> "Jinju Lantern Festival"
      "14th Daegu Flower Festival 2024" -> "Daegu Flower Festival"
    """
    if not name_en:
        return ""

    s = str(name_en)

    # 1) "25th", "14th", "3rd", "2nd", "1st" 같은 서수 제거
    s = re.sub(r"\b\d+(st|nd|rd|th)\b", "", s, flags=re.IGNORECASE)

    # 2) 연도/숫자 토큰 제거 (2~4자리 숫자)
    s = re.sub(r"\b\d{2,4}\b", "", s)

    # 3) 여분 공백 정리
    s = " ".join(s.split())

    return s


# -------------------------------------------------------------
# 영어 축제명 → 3~5자 모노그램(알파벳)
# -------------------------------------------------------------
def _build_monogram_from_english(
    name_en: str,
    min_len: int = 3,
    max_len: int = 5,
) -> str:
    """
    영어 축제명에서 라틴 알파벳만 추출해 3~5자의 모노그램(대문자) 생성.
    """
    if not name_en:
        raise ValueError("festival_name_en 이 비어 있어서 모노그램을 만들 수 없습니다.")

    words: List[str] = re.findall(r"[A-Za-z]+", name_en)
    if not words:
        raise ValueError(f"영어 축제명에서 알파벳 단어를 찾을 수 없습니다: {name_en!r}")

    initials = "".join(w[0] for w in words if w)[0:max_len].upper()
    letters: List[str] = list(initials)

    if len(letters) < min_len:
        for w in words:
            for ch in w[1:]:
                if ch.isalpha():
                    letters.append(ch.upper())
                    if len(letters) >= max_len:
                        break
            if len(letters) >= max_len:
                break

    monogram = "".join(letters[:max_len])
    if len(monogram) < min_len:
        raise ValueError(
            f"모노그램 길이가 {min_len}보다 짧습니다: {monogram!r} (from {name_en!r})"
        )
    return monogram


# -------------------------------------------------------------
# 1) 타이포그래피 로고 프롬프트 (모노그램 + 아래 풀네임)
#   👉 배경 단색 + 카드/액자/일러스트 절대 금지로 더 강하게
# -------------------------------------------------------------
def _build_logo_typography_prompt_en(
    festival_name_en: str,
    monogram_text: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    """
    축제 알파벳 타이포그래피 로고용 Seedream 영어 프롬프트.

    요구사항 핵심
    1) 큰 모노그램 알파벳: monogram_text
    2) 그 바로 아래, 같은 중심선에 전체 영어 축제명: festival_name_en
    """

    def _n(s: str) -> str:
        return " ".join(str(s or "").split())

    festival_name_en = _n(festival_name_en)
    monogram_text = _n(monogram_text)
    base_scene_en = _n(base_scene_en)
    details_phrase_en = _n(details_phrase_en)
    spaced_letters = " ".join(list(monogram_text))

    prompt = (
        # 전체 컨셉
        "Minimal square 1:1 festival typography logo on a perfectly flat single-color background. "
        "This is a clean logo, not a poster and not a scene illustration. "

        # 포스터는 색/무드 참고용만
        "Use the attached poster image ONLY as reference for color palette and overall mood, "
        f"as suggested by {base_scene_en} and {details_phrase_en}. "
        "Do NOT copy the poster layout, drawings, or characters. "

        # 배경: 딱 한 가지 색
        "Fill the entire canvas with exactly ONE solid flat background color from edge to edge. "
        "Choose this background color from the dominant colors of the poster. "
        "There must be NO panels, NO cards, NO separate boxes, NO frames, NO gradients, "
        "NO textures, NO noise, NO paper effect and NO second background color. "

        # -------------------------------
        # 1) 큰 모노그램 알파벳
        # -------------------------------
        f"In the visual center of the canvas, place a very large bold monogram made ONLY from the letters \"{monogram_text}\". "
        f"Use exactly these characters: {spaced_letters}. "
        "The monogram must look like a designed logo mark, not a default font. "
        "You may slightly adjust spacing or connect strokes, but every letter must stay clearly readable. "
        "Style the letters to reflect the festival theme using shapes and shading only, "
        "while keeping edges sharp and vector-like. "

        # -------------------------------
        # 2) 그 바로 아래, 축제 풀네임 1줄
        # -------------------------------
        f"Directly BELOW this monogram, on the same vertical centerline, add ONE subtitle line with the full English festival name: \"{festival_name_en}\". "
        "There MUST be exactly two separate pieces of text in the image and BOTH are REQUIRED: "
        f"1) the large monogram \"{monogram_text}\", and "
        f"2) the subtitle line \"{festival_name_en}\". "
        "If the subtitle is missing, the design is incorrect and must be fixed. "

        "Place the subtitle close to the monogram (not far away at the bottom of the canvas), "
        "with a small comfortable gap between them. "
        "Horizontally center the subtitle under the monogram so that their widths visually match. "
        "Make the subtitle clearly readable: about one third of the monogram letter height, "
        "with strokes thick enough to remain legible after scaling. "
        "Use a clean modern sans-serif typeface without decorative effects. "

        # 텍스트 제한
        "Do NOT add any other text besides these two: the monogram and the subtitle line. "
        "No extra words, no abbreviations like Fes or Fest, no years, no dates, no edition numbers, "
        "no slogans, no taglines, no URLs, no hashtags, and no labels such as ESTD. "
        "Do NOT use Korean or any non-Latin characters. "

        # 기타 금지 요소
        "Do NOT draw icons, pictograms, hands, puppets, characters, instruments or other objects around the logo. "
        "All visible shapes other than the background must be part of the monogram or the subtitle text only. "
        "Do NOT show posters, banners, signboards, mockups, shadows under the canvas, "
        "embossing, foil stamping, or 3D extrusions. "
        "Focus purely on a strong monogram plus one subtitle line on a single flat background color. "
        "Do not draw quotation marks."
    )
    return prompt.strip()



# -------------------------------------------------------------
# 2) write_logo_typography: Seedream 입력 JSON 생성
# -------------------------------------------------------------
def write_logo_typography(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """타이포그래피 로고(2048x2048)용 Seedream 입력 JSON 생성."""

    festival_name_ko_clean = _strip_edition_from_name_ko(festival_name_ko)

    translated = _translate_festival_ko_to_en(
        festival_name_ko=festival_name_ko_clean,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )
    name_en_raw = translated.get("name_en", "")
    period_en = translated.get("period_en", "")
    location_en = translated.get("location_en", "")

    name_en = _strip_numbers_from_english_name(name_en_raw)

    if not name_en:
        raise ValueError(
            f"영어 축제명이 비어 있어 알파벳 로고를 생성할 수 없습니다. (원본: {name_en_raw!r})"
        )

    monogram_text = _build_monogram_from_english(name_en, min_len=3, max_len=5)

    scene_info = _build_scene_phrase_from_poster(
        poster_image_url=poster_image_url,
        festival_name_en=name_en,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )

    prompt = _build_logo_typography_prompt_en(
        festival_name_en=name_en,
        monogram_text=monogram_text,
        base_scene_en=scene_info["base_scene_en"],
        details_phrase_en=scene_info["details_phrase_en"],
    )

    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": LOGO_TYPO_WIDTH_PX,
        "height": LOGO_TYPO_HEIGHT_PX,
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
        "festival_name_en": name_en,
        "monogram_text": monogram_text,
        "festival_base_name_ko": str(festival_name_ko or ""),
        "festival_base_name_ko_clean": str(festival_name_ko_clean or ""),
        "festival_base_period_ko": str(festival_period_ko or ""),
        "festival_base_location_ko": str(festival_location_ko or ""),
    }

    return seedream_input


# -------------------------------------------------------------
# 3) 저장 디렉터리
# -------------------------------------------------------------
def _get_logo_typography_save_dir() -> Path:
    env_dir = os.getenv("LOGO_TYPOGRAPHY_SAVE_DIR")
    if env_dir:
        p = Path(env_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    return DATA_ROOT / "logo_typography"


# -------------------------------------------------------------
# 4) create_logo_typography: Seedream 호출 + 저장
# -------------------------------------------------------------
def create_logo_typography(
    seedream_input: Dict[str, Any],
    save_dir: Path | None = None,
    prefix: str = "logo_typography_",
) -> Dict[str, Any]:
    poster_url = _extract_poster_url_from_input(seedream_input)
    if not poster_url:
        raise ValueError(
            "seedream_input.image_input 에 참조 포스터 이미지 URL/경로가 없습니다."
        )

    img_bytes = _download_image_bytes(poster_url)
    image_file = BytesIO(img_bytes)

    prompt = seedream_input.get("prompt", "")
    size = seedream_input.get("size", "custom")
    width = int(seedream_input.get("width", LOGO_TYPO_WIDTH_PX))
    height = int(seedream_input.get("height", LOGO_TYPO_HEIGHT_PX))
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

    model_name = os.getenv("LOGO_TYPOGRAPHY_MODEL", "bytedance/seedream-4")

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
                f"Seedream model error during typography logo generation: {e}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error during typography logo generation: {e}"
            )

    if output is None:
        raise RuntimeError(
            f"Seedream model error during typography logo generation after retries: {last_err}"
        )

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]

    if save_dir is not None:
        save_base = Path(save_dir)
    else:
        save_base = _get_logo_typography_save_dir()
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
        "monogram_text": str(seedream_input.get("monogram_text", "")),
    }


# -------------------------------------------------------------
# 5) editor 저장용 헬퍼
# -------------------------------------------------------------
def run_logo_typography_to_editor(
    run_id: int,
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    seedream_input = write_logo_typography(
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

    create_result = create_logo_typography(
        seedream_input,
        save_dir=before_image_dir,
        prefix="logo_typography_",
    )

    image_filename = create_result["image_filename"]

    base_url = os.getenv("ACC_AI_BASE_URL", "http://localhost:5000").rstrip("/")
    static_prefix = "/static"
    image_url = f"{base_url}{static_prefix}/editor/{run_id}/before_image/{image_filename}"

    result: Dict[str, Any] = {
        "type": LOGO_TYPO_TYPE,
        "pro_name": LOGO_TYPO_PRO_NAME,
        "festival_name_en": create_result["festival_name_en"],
        "monogram_text": create_result["monogram_text"],
        "width": LOGO_TYPO_WIDTH_PX,
        "height": LOGO_TYPO_HEIGHT_PX,
        "image_url": image_url,
    }

    json_path = before_data_dir / "logo_typography.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


# -------------------------------------------------------------
# 6) CLI main
# -------------------------------------------------------------
def main() -> None:
    """
    python app/service/logo/make_logo_typography.py
    """

    run_id = 5

    poster_image_url = r"C:\final_project\ACC\acc-ai\app\data\banner\arco.png"
    festival_name_ko = "예술 인형 축제"
    festival_period_ko = "2025.11.04 ~ 2025.11.09"
    festival_location_ko = "아르코꿈밭극장, 텃밭스튜디오"

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

    result = run_logo_typography_to_editor(
        run_id=run_id,
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    editor_root = DATA_ROOT / "editor" / str(run_id)
    json_path = editor_root / "before_data" / "logo_typography.json"
    image_dir = editor_root / "before_image"

    print("✅ typography logo 생성 + editor 저장 완료")
    print("  type             :", result.get("type"))
    print("  pro_name         :", result.get("pro_name"))
    print("  festival_name_en :", result.get("festival_name_en"))
    print("  monogram_text    :", result.get("monogram_text"))
    print("  width x height   :", result.get("width"), "x", result.get("height"))
    print("  image_url        :", result.get("image_url"))
    print("  json_path        :", json_path)
    print("  image_dir        :", image_dir)


if __name__ == "__main__":
    main()
