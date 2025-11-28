# -*- coding: utf-8 -*-
"""
app/service/logo/make_logo_typography.py

축제 알파벳 타이포그래피 로고(정사각형 2048x2048)용
Seedream 입력/프롬프트 생성 + 생성 이미지 저장 모듈.

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
  7) run_logo_typography_to_editor(...) 로 p_no 기준 acc-front/public/data/promotion 경로에
     생성 이미지를 저장하고, DB 저장용 메타 정보를 반환한다.
  8) python make_logo_typography.py 로 단독 실행할 수 있다.

※ 로고 이미지 안에 들어가는 텍스트 규칙
- 메인: 모노그램 알파벳 (예: GAF, BMF)
- 서브: 영어 축제명에서 연도/숫자/회차를 제거한 "축제 이름"만
  예) "2025 Boryeong Mud Festival" -> "Boryeong Mud Festival"

DB 저장용 리턴 예시:

{
  "db_file_type": "logo_typography",
  "type": "image",
  "db_file_path": "C:\\final_project\\ACC\\acc-front\\public\\data\\promotion\\M000001\\P000001\\logo\\logo_typography_....png",
  "type_ko": "타이포그래피 로고"
}

전제 환경변수
- OPENAI_API_KEY                  : OpenAI API 키
- BANNER_LLM_MODEL                : (선택) 배너/버스/로고용 LLM, 기본값 "gpt-4o-mini"
- LOGO_TYPOGRAPHY_MODEL           : (선택) 기본값 "bytedance/seedream-4"
- LOGO_TYPOGRAPHY_SAVE_DIR        : (선택) create_logo_typography 단독 사용 시 저장 경로
- ACC_AI_BASE_URL                 : (선택) (이 모듈에서는 사용 안 함)
- ACC_MEMBER_NO                   : (선택) 프로모션 파일 경로용 회원번호, 기본값 "M000001"
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import replicate
from dotenv import load_dotenv
from replicate.exceptions import ModelError

# -------------------------------------------------------------
# 프로젝트 루트 및 .env 로딩 + sys.path 설정
# -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # .../ACC/acc-ai
DATA_ROOT = PROJECT_ROOT / "app" / "data"

LOGO_TYPO_TYPE = "logo_typography"
LOGO_TYPO_PRO_NAME = "타이포그래피 로고"
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
    _save_image_from_file_output,
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

    예)
      "Goheung Aerospace Festival" -> "GAF"
      "Boryeong Mud Festival"     -> "BMF"
      "Daejeon Guitar Festival"   -> "DGF"
    """
    if not name_en:
        raise ValueError("festival_name_en 이 비어 있어서 모노그램을 만들 수 없습니다.")

    # 영어 단어들만 추출
    words: List[str] = re.findall(r"[A-Za-z]+", name_en)
    if not words:
        raise ValueError(f"영어 축제명에서 알파벳 단어를 찾을 수 없습니다: {name_en!r}")

    # 각 단어의 첫 글자 → GAF, DGF 같은 형태
    initials = "".join(w[0] for w in words if w)[0:max_len].upper()
    letters: List[str] = list(initials)

    # 너무 짧으면 단어 안쪽에서도 추가로 알파벳 채워 넣기
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
# -------------------------------------------------------------
def _build_logo_typography_prompt_en(
    festival_name_en: str,
    monogram_text: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    """
    축제 알파벳 타이포그래피 로고용 Seedream 영어 프롬프트.

    규칙 (이미지 기준)
    1) 배경은 무조건 단색
    2) 가운데에 모노그램 텍스트(알파벳만) - 가로 한 줄만
    3) 모노그램 텍스트는 축제 테마/무드에 맞게 디자인
    4) 그 바로 아래 한 줄로 전체 영어 축제명
    """

    def _n(s: str) -> str:
        return " ".join(str(s or "").split())

    festival_name_en = _n(festival_name_en)
    monogram_text = _n(monogram_text)
    base_scene_en = _n(base_scene_en)
    details_phrase_en = _n(details_phrase_en)
    spaced_letters = " ".join(list(monogram_text))

    prompt = f"""
Square 1:1 clean logo illustration.

Background
- Use a single solid color background only.
- Do not use any gradients, patterns, textures, noise, paper effects, or images.
- The background color and accent colors should reflect the festival's theme, mood, and atmosphere:
  {base_scene_en} {details_phrase_en}

Central monogram
- In the exact center of the canvas, create a bold custom monogram using ONLY the letters "{monogram_text}".
- Use exactly these characters, in this exact left-to-right order: {spaced_letters}.
- Arrange ALL letters on one single straight horizontal line.
- Do NOT stack the letters, do NOT curve them, and do NOT place them diagonally.
- Each letter must be upright, not rotated, clearly readable, and evenly aligned on the same baseline.
- The monogram should look like a distinctive logo mark, not like default typed text, and should visually express the festival concept.

Festival name
- Directly below the monogram, place one small thin line of English text with the full festival name:
  "{festival_name_en}"
- Center-align this text under the monogram.
- The text width should be similar to the monogram width, with comfortable breathing space between them.
- Use a simple, clean sans-serif style that is easy to read.

Hard constraints
- The final image must contain ONLY:
  1) the solid color background,
  2) the central horizontal monogram,
  3) the single small line of the festival name under it.
- Do NOT add any extra words, dates, numbers, Korean characters, slogans, taglines, icons, symbols, or logos.
- Do NOT draw frames, borders, or additional decorative text.
"""

    # 공백 정리해서 한 줄 프로ンプ트로
    return " ".join(prompt.split())


# -------------------------------------------------------------
# 2) write_logo_typography: Seedream 입력 JSON 생성
# -------------------------------------------------------------
def write_logo_typography(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    축제 알파벳 타이포그래피 로고(2048x2048)용 Seedream 입력 JSON 생성.

    - festival_name_ko 에 '제 7회', '제 15회' 등이 포함되어 있어도
      회차를 제거한 순수 축제명만 번역에 사용한다.
    - 영어 축제명에서 연도/숫자를 제거한 뒤 3~5자 모노그램을 만든다.
      (예: "2025 Boryeong Mud Festival" → "Boryeong Mud Festival" → BMF)
    - 이미지에는 한글은 직접 사용하지 않고,
      모노그램 + 영어 풀 네임(연도/회차 제거된 축제명)만 사용하도록 프롬프트를 구성한다.
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

    # 1-1) 영어 축제명에서 연도/숫자/회차 제거
    name_en = _strip_numbers_from_english_name(name_en_raw)

    if not name_en:
        raise ValueError(
            f"영어 축제명이 비어 있어 알파벳 로고를 생성할 수 없습니다. (원본: {name_en_raw!r})"
        )

    # 2) 영어 축제명 → 모노그램(3~5자 알파벳)
    monogram_text = _build_monogram_from_english(name_en, min_len=3, max_len=5)

    # 3) 포스터 이미지 분석 → 색감/무드/키워드 정리
    scene_info = _build_scene_phrase_from_poster(
        poster_image_url=poster_image_url,
        festival_name_en=name_en,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )

    # 4) 최종 프롬프트 조립
    prompt = _build_logo_typography_prompt_en(
        festival_name_en=name_en,
        monogram_text=monogram_text,
        base_scene_en=scene_info["base_scene_en"],
        details_phrase_en=scene_info["details_phrase_en"],
    )

    # 5) Seedream / Replicate 입력 JSON 구성
    #    -> 포스터 이미지는 Seedream에 보내지 않고, LLM 분석용으로만 사용.
    seedream_input: Dict[str, Any] = {
        "size": "custom",  # Seedream 허용값: "1K", "2K", "4K", "custom"
        "width": LOGO_TYPO_WIDTH_PX,
        "height": LOGO_TYPO_HEIGHT_PX,
        "prompt": prompt,
        "max_images": 1,
        "aspect_ratio": "1:1",
        "enhance_prompt": True,
        "sequential_image_generation": "disabled",
        # Seedream에는 이미지 입력을 보내지 않는다 (텍스트로만 생성)
        "image_input": [],
        # 결과 조립용으로 필요한 원본 정보
        "poster_image_url": poster_image_url,
        "festival_name_en": name_en,
        "monogram_text": monogram_text,
        "festival_base_name_ko": str(festival_name_ko or ""),
        "festival_base_name_ko_clean": str(festival_name_ko_clean or ""),
        "festival_base_period_ko": str(festival_period_ko or ""),
        "festival_base_location_ko": str(festival_location_ko or ""),
    }

    return seedream_input


# -------------------------------------------------------------
# 3) 저장 디렉터리 (create_logo_typography 단독 사용용)
# -------------------------------------------------------------
def _get_logo_typography_save_dir() -> Path:
    """
    LOGO_TYPOGRAPHY_SAVE_DIR 환경변수가 있으면:
      - 절대경로면 그대로 사용
      - 상대경로면 PROJECT_ROOT 기준으로 사용
    없으면:
      - PROJECT_ROOT/app/data/logo_typography 사용

    ※ run_logo_typography_to_editor 에서는 사용하지 않고,
       create_logo_typography 단독 사용 시에만 사용.
    """
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
    """
    write_logo_typography(...) 에서 만든 Seedream 입력 JSON을 그대로 받아
    Replicate(bytedance/seedream-4 또는 LOGO_TYPOGRAPHY_MODEL)에
    텍스트 프롬프트만 전달해 실제 2048x2048 타이포그래피 로고 이미지를 생성하고,
    생성된 이미지를 로컬에 저장한다.
    """

    prompt = seedream_input.get("prompt", "")
    size = seedream_input.get("size", "custom")
    width = int(seedream_input.get("width", LOGO_TYPO_WIDTH_PX))
    height = int(seedream_input.get("height", LOGO_TYPO_HEIGHT_PX))
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
        # 이미지 conditioning 없이 텍스트만 사용
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
# 5) editor → DB 경로용 헬퍼 (p_no 사용)
# -------------------------------------------------------------
def run_logo_typography_to_editor(
    p_no: str,
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    입력:
        p_no
        poster_image_url
        festival_name_ko
        festival_period_ko
        festival_location_ko

    동작:
      1) write_logo_typography(...) 로 Seedream 입력용 seedream_input 생성
      2) create_logo_typography(..., save_dir=로고 저장 디렉터리) 로
         실제 타이포그래피 로고 이미지를 생성하고,
         acc-front/public/data/promotion/<member_no>/<p_no>/logo/ 아래에 저장한다.
      3) DB 저장용 메타 정보 딕셔너리를 반환한다.

    반환:
      {
        "db_file_type": "logo_typography",
        "type": "image",
        "db_file_path": "C:\\...\\acc-front\\public\\data\\promotion\\M000001\\{p_no}\\logo\\logo_typography_....png",
        "type_ko": "타이포그래피 로고"
      }
    """

    # 1) 프롬프트 생성
    seedream_input = write_logo_typography(
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    # 2) 저장 디렉터리: acc-front/public/data/promotion/<member_no>/<p_no>/logo
    member_no = os.getenv("ACC_MEMBER_NO", "M000001")
    front_root = PROJECT_ROOT.parent / "acc-front"
    logo_dir = (
        front_root
        / "public"
        / "data"
        / "promotion"
        / member_no
        / str(p_no)
        / "logo"
    )
    logo_dir.mkdir(parents=True, exist_ok=True)

    # 3) 이미지 생성
    create_result = create_logo_typography(
        seedream_input,
        save_dir=logo_dir,
        prefix="logo_typography_",
    )

    # 4) 실제 저장된 파일 경로를 그대로 사용
    db_file_path = str(create_result["image_path"])

    result: Dict[str, Any] = {
        "db_file_type": LOGO_TYPO_TYPE,      # "logo_typography"
        "type": "image",
        "db_file_path": db_file_path,
        "type_ko": LOGO_TYPO_PRO_NAME,       # "타이포그래피 로고"
    }

    return result


# -------------------------------------------------------------
# 6) CLI main
# -------------------------------------------------------------
def main() -> None:
    """
    python app/service/logo/make_logo_typography.py
    """

    # 1) 여기 값만 네가 원하는 걸로 수정해서 쓰면 됨
    p_no = "10"

    poster_image_url = r"C:\final_project\ACC\acc-ai\app\data\banner\geoje.png"
    festival_name_ko = "거제몽돌해변축제"
    festival_period_ko = "2013.07.13 ~ 2013.07.14"
    festival_location_ko = "학동흑진주몽돌해변"

    # 2) 필수값 체크
    missing = []
    if not p_no:
        missing.append("p_no")
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

    # 3) 실제 실행 (Dict 리턴)
    result = run_logo_typography_to_editor(
        p_no=p_no,
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    # stdout으로는 값 4개만 딱 찍어주기
    db_file_type = result.get("db_file_type", "")
    type_ = result.get("type", "")
    db_file_path = result.get("db_file_path", "")
    type_ko = result.get("type_ko", "")

    print(db_file_type)
    print(type_)
    print(db_file_path)
    print(type_ko)


if __name__ == "__main__":
    main()
