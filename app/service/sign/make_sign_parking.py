# -*- coding: utf-8 -*-
"""
app/service/sign/make_sign_parking.py

축제 주차장 입간판 표지용(세로형 1024x1862) Seedream 모듈.

역할
- 참고용 마스코트/포스터 이미지(URL 또는 로컬 파일 경로)와 축제 정보(한글)를 입력받아서
  1) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  2) 포스터/마스코트 이미지를 시각적으로 분석해서 축제 테마/무드 정보를 영어로 만든 뒤
  3) 축제명/테마를 이용해 세로형 주차장 입간판용 프롬프트를 조립한다. (write_sign_parking)
  4) 해당 JSON을 받아 Replicate(Seedream)를 호출해 실제 이미지를 생성하고 저장한다. (create_sign_parking)
  5) run_sign_parking_to_editor(...) 로 run_id 기준 editor 폴더에 JSON/이미지 사본을 저장한다.
  6) python make_sign_parking.py 로 단독 실행할 수 있다.

결과 JSON 형태 (editor용 최소 정보):

{
  "type": "sign_parking",
  "pro_name": "주차장 표지판",
  "festival_name_en": "Goheung Aerospace Festival",
  "width": 1024,
  "height": 1862,
  "image_url": "http://localhost:5000/static/editor/10/before_image/sign_parking.png"
}

※ festival_name_en 은 '제 N회' 를 제거한 기본 영어 축제명(예: Goheung Aerospace Festival).
※ 실제 이미지 안에는 "PARKING"과 오른쪽 화살표, 마스코트만 등장하고 축제명 텍스트는 사용하지 않는다.

전제 환경변수
- OPENAI_API_KEY             : OpenAI API 키 (banner_khs.make_road_banner 내부에서 사용)
- BANNER_LLM_MODEL           : (선택) 배너/버스/표지판용 LLM, 기본값 "gpt-4o-mini"
- SIGN_PARKING_MODEL         : (선택) 기본값 "bytedance/seedream-4"
- SIGN_PARKING_SAVE_DIR      : (선택) 단독 create_sign_parking 사용 시 저장 경로
- EDITOR_STATIC_BASE_URL     : (선택) editor 정적 URL prefix, 기본값 "http://localhost:5000/static/editor"
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Tuple, Optional

import replicate
from dotenv import load_dotenv
from replicate.exceptions import ModelError
from openai import OpenAI

# -------------------------------------------------------------
# 프로젝트 루트 및 .env 로딩 + sys.path 설정
# -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / "app" / "data"

# 주차장 입간판 고정 스펙
SIGN_PARKING_TYPE = "sign_parking"
SIGN_PARKING_PRO_NAME = "주차장 표지판"
SIGN_PARKING_WIDTH = 1024
SIGN_PARKING_HEIGHT = 1862

# editor 정적 URL prefix (이미지 URL 만들 때 사용)
EDITOR_STATIC_BASE_URL = os.getenv(
    "EDITOR_STATIC_BASE_URL",
    "http://localhost:5000/static/editor",
)

# .env 로딩
env_path = PROJECT_ROOT / ".env"
load_dotenv(env_path)

# app 패키지 import를 위해 루트를 sys.path에 추가
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# -------------------------------------------------------------
# 기존 road_banner 유틸 재사용
# -------------------------------------------------------------
from app.service.banner_khs.make_road_banner import (  # type: ignore
    _translate_festival_ko_to_en,
    _build_scene_phrase_from_poster,
    _save_image_from_file_output,
    _download_image_bytes,
)

# -------------------------------------------------------------
# OpenAI 클라이언트 (LLM + Vision 검사용)
# -------------------------------------------------------------
_client: Optional[OpenAI] = None


def _get_openai_client() -> OpenAI:
    """OPENAI_API_KEY 를 사용하는 전역 OpenAI 클라이언트 (한 번만 생성)."""
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


# -------------------------------------------------------------
# 1) 한글 축제명에서 회차/축제명 분리 (필요시)
# -------------------------------------------------------------
def _split_festival_count_and_name(full_name_ko: str) -> Tuple[str, str]:
    """
    입력: "제7회 담양산타축제", "제 7회 담양산타축제", "담양산타축제" 등

    반환:
      (festival_count, festival_name_ko)
    """
    text = str(full_name_ko or "").strip()
    if not text:
        return "제 1회", ""

    m = re.match(r"^\s*(제\s*\d+\s*회)\s*(.*)$", text)
    if not m:
        return "제 1회", text

    raw_count = m.group(1)
    rest_name = m.group(2)

    normalized_count = re.sub(r"\s+", "", raw_count)

    name_ko = rest_name.strip() if rest_name.strip() else text
    return normalized_count, name_ko


# -------------------------------------------------------------
# 2) 문자열 정규화 유틸
# -------------------------------------------------------------
def _norm(s: str) -> str:
    return " ".join(str(s or "").split())


# -------------------------------------------------------------
# 3) 주차장 입간판 프롬프트 조립
# -------------------------------------------------------------
def _build_sign_parking_prompt_en(
    festival_name_en: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    """
    세로형 축제 주차 안내 일러스트용 Seedream 프롬프트.

    목표 규칙
    1) "PARKING" 한 단어만 텍스트로 사용 (전부 대문자, 가로 한 줄).
    2) 오른쪽을 가리키는 화살표(→) 1개만 사용, 매우 크게.
    3) 마스코트가 함께 나오되, 글자/화살표를 가리지 않음.
    4) 배경은 축제/마스코트에 어울리는 일러스트 느낌, 실사/사진 금지.
    5) 그 외의 모든 글자, 숫자, 로고, 간판 모양은 절대 그리지 않음.
    """

    base_scene_en = _norm(base_scene_en)
    details_phrase_en = _norm(details_phrase_en)

    prompt = (
        # 0. 참고 이미지 텍스트 무시 + 축제 분위기만 사용
        "Create a tall vertical festival parking illustration. "
        "Ignore all text, letters, and numbers in the attached image. "
        "Use only its colours, shapes, and the festive mood described as "
        f"{base_scene_en}, {details_phrase_en}. "

        # 1. PARKING 텍스트 – 좌우 꽉 차게, 진한 색
        "In the central area, write the word \"PARKING\" in ALL CAPITAL letters, on one horizontal line. "
        "Center it horizontally and make it very bold and thick, using a dark, high-contrast colour. "
        "Let the word stretch almost from the left edge to the right edge, with a small safe margin. "
        "Do NOT rotate the word, do NOT stack the letters vertically, and do NOT curve or distort the text. "
        "Do not use a light grey or faint colour for this word. "

        # 2. 오른쪽 화살표 – 하나, 엄청 크고 꽉 찬 색
        "Place exactly one huge horizontal arrow pointing to the RIGHT (like a bold \"→\" shape). "
        "The arrow must be a solid filled shape with a very thick body, not just an outline. "
        "Use a dark, high-contrast colour similar to or slightly brighter than the PARKING text, "
        "never a light grey or transparent colour. "
        "Center the arrow horizontally and make its width similar to or slightly larger than the word \"PARKING\", "
        "and its height large enough to look as strong and bold as the text. "
        "Position the arrow directly above or directly below the word, with a clear gap so the two elements "
        "read together as a single parking sign. "
        "Do not draw any up, down, or left arrows, and do not draw more than one arrow. "

        # 3. 마스코트 – 글자/화살표 보조 역할
        "Add the festival mascot as a large, cute character near the PARKING-and-arrow block, "
        "as if guiding visitors in that direction. "
        "The mascot should be clearly visible but slightly smaller than the word and the arrow, "
        "and it must not cover or overlap the text or the arrow. "

        # 4. 배경 – 축제스럽지만 글자 없는 일러스트
        "Use a simple, non-photorealistic illustrated background that matches the mascot style "
        "and feels like a festival. "
        "Do NOT use any photographic, realistic, or semi-realistic background; "
        "draw everything as a clean, flat cartoon-style illustration. "
        "Keep the background clean and not too busy so that \"PARKING\" and the arrow remain "
        "the most eye-catching elements. "

        # 5. 텍스트/간판 금지 규칙
        "The ONLY text allowed in the whole image is the single word \"PARKING\". "
        "Do NOT add any other English or Korean words, numbers, logos, shop signs, banners, or small scribbles "
        "that look like letters anywhere in the image. "
        "Do not draw quotation marks."
    )

    return prompt.strip()


# -------------------------------------------------------------
# 3-1) 생성된 이미지를 LLM(Vision)으로 검증
# -------------------------------------------------------------
def _validate_sign_parking_image_with_llm(image_path: str) -> Dict[str, Any]:
    """
    생성된 주차장 표지 이미지를 LLM(비전)으로 검사한다.

    체크 규칙:
      - 가로 한 줄의 "PARKING" 텍스트가 있는가 (대략 중앙, 크게)?
      - 오른쪽(→)을 가리키는 화살표가 1개 있는가 (크고 명확하게)?
      - 다른 읽을 수 있는 텍스트가 없는가?
      - 마스코트(캐릭터)가 있는가?
      - 전체가 일러스트 스타일이고, 실사/사진 느낌이 아닌가?

    반환 예:
      {
        "ok": true,
        "has_parking": true,
        "has_right_arrow": true,
        "has_other_text": false,
        "has_mascot": true,
        "is_illustration": true,
        "reason": "..."
      }
    """
    client = _get_openai_client()
    model = os.getenv("BANNER_LLM_MODEL", "gpt-4o-mini")

    img_path = Path(image_path)
    img_bytes = img_path.read_bytes()
    img_b64 = base64.b64encode(img_bytes).decode("ascii")
    data_url = f"data:image/png;base64,{img_b64}"

    system_msg = (
        "You are a strict inspector for a festival parking sign illustration. "
        "You must look at the image and check if it follows the layout rules. "
        "Always answer ONLY with a single JSON object, no extra text."
    )

    user_text = """
Check this image of a parking sign illustration and answer whether it obeys ALL of the following rules:

1) There is a single horizontal word "PARKING" in all capital letters.
   - It should be written in one horizontal line, not vertical, not curved.
   - It should be large and near the center area, clearly readable.

2) There is exactly one big arrow pointing to the RIGHT (→).
   - No up, down, or left arrows.
   - The right arrow should be thick and very visible.

3) There is no other readable text besides the word "PARKING".
   - No festival name, shop signs, logos, numbers, or small text.

4) There is a mascot or character figure included somewhere in the image.

5) The overall style is an illustration/cartoon, not a photographic or realistic photo.

Return a JSON object with these fields:

{
  "ok": boolean,              // true only if ALL rules are satisfied
  "has_parking": boolean,
  "has_right_arrow": boolean,
  "has_other_text": boolean,  // true if any extra text is visible
  "has_mascot": boolean,
  "is_illustration": boolean,
  "reason": string            // short English explanation
}

Answer ONLY with valid JSON. Do not add any commentary.
""".strip()

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_msg},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_text},
                    {"type": "input_image", "image_url": data_url},
                ],
            },
        ],
    )

    try:
        raw_text = resp.output[0].content[0].text  # type: ignore[attr-defined]
    except Exception as e:
        raise RuntimeError(
            f"LLM validation response parsing failed: {e!r} / raw={resp!r}"
        )

    raw_text = (raw_text or "").strip()

    try:
        data = json.loads(raw_text)
    except Exception as e:
        # JSON 파싱 실패하면 무조건 실패로 간주
        return {
            "ok": False,
            "has_parking": False,
            "has_right_arrow": False,
            "has_other_text": True,
            "has_mascot": False,
            "is_illustration": False,
            "reason": f"JSON parse error: {e!r}, raw={raw_text[:200]}",
        }

    return {
        "ok": bool(data.get("ok", False)),
        "has_parking": bool(data.get("has_parking", False)),
        "has_right_arrow": bool(data.get("has_right_arrow", False)),
        "has_other_text": bool(data.get("has_other_text", True)),
        "has_mascot": bool(data.get("has_mascot", False)),
        "is_illustration": bool(data.get("is_illustration", False)),
        "reason": str(data.get("reason", "")).strip(),
    }


# -------------------------------------------------------------
# 4) write_sign_parking: Seedream 입력 JSON 생성
# -------------------------------------------------------------
def write_sign_parking(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    세로형 주차장 입간판(1024x1862)용 Seedream 입력 JSON을 생성한다.

    - festival_name_ko: "제15회 고흥 우주항공 축제" 또는 "고흥 우주항공 축제" 등
      → 내부에서 회차/축제명을 분리해 영어 축제명 번역에 사용한다.
      (단, 실제 이미지 안에는 축제명 텍스트를 사용하지 않는다.)
    """

    # 1) 회차 / 축제명 분리 (회차는 번역 품질 향상을 위한 용도로만 사용)
    _, pure_name_ko = _split_festival_count_and_name(festival_name_ko)

    # 2) 한글 축제 정보 → 영어 번역 (테마/씬 묘사용)
    translated = _translate_festival_ko_to_en(
        festival_name_ko=pure_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )
    name_en = translated["name_en"]
    period_en = translated["period_en"]
    location_en = translated["location_en"]

    # 3) 포스터 이미지 분석 → 축제 씬/무드 묘사 얻기
    scene_info = _build_scene_phrase_from_poster(
        poster_image_url=poster_image_url,
        festival_name_en=name_en,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )

    # 4) 최종 프롬프트 조립
    prompt = _build_sign_parking_prompt_en(
        festival_name_en=name_en,
        base_scene_en=scene_info["base_scene_en"],
        details_phrase_en=scene_info["details_phrase_en"],
    )

    # 5) Seedream / Replicate 입력 JSON 구성
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": SIGN_PARKING_WIDTH,
        "height": SIGN_PARKING_HEIGHT,
        "prompt": prompt,
        "max_images": 1,
        "aspect_ratio": "9:16",  # 세로형 비율
        "enhance_prompt": True,
        "sequential_image_generation": "disabled",
        "image_input": [
            {
                "type": "image_url",
                "url": poster_image_url,
            }
        ],
        # 원본 축제 정보 (메타용)
        "festival_name_ko": festival_name_ko,
        "festival_name_en": name_en,
        "festival_period_ko": festival_period_ko,
        "festival_location_ko": festival_location_ko,
    }

    return seedream_input


# -------------------------------------------------------------
# 5) 주차장 입간판 저장 디렉터리 결정
# -------------------------------------------------------------
def _get_sign_parking_save_dir() -> Path:
    """
    SIGN_PARKING_SAVE_DIR 환경변수가 있으면:
      - 절대경로면 그대로 사용
      - 상대경로면 PROJECT_ROOT 기준으로 사용
    없으면:
      - PROJECT_ROOT/app/data/sign_parking 사용
    """
    env_dir = os.getenv("SIGN_PARKING_SAVE_DIR")
    if env_dir:
        p = Path(env_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    return DATA_ROOT / "sign_parking"


# -------------------------------------------------------------
# 6) create_sign_parking: Seedream JSON → Replicate 호출 → 이미지 저장
#     + LLM으로 규칙 검증, 일정 횟수 내 재생성
# -------------------------------------------------------------
def create_sign_parking(
    seedream_input: Dict[str, Any],
    save_dir: Path | None = None,
    prefix: str = "sign_parking_",
    max_generate_tries: int = 3,  # LLM 검증 포함 최대 재생성 횟수
) -> Dict[str, Any]:
    """
    write_sign_parking(...) 에서 만든 Seedream 입력 JSON을 그대로 받아
    1) image_input 의 포스터 URL/경로를 이용해 이미지를 다운로드하고,
    2) Replicate(bytedance/seedream-4 또는 SIGN_PARKING_MODEL)에
       prompt + image_input과 함께 전달해 실제 세로형 주차장 입간판 이미지를 생성하고,
    3) 생성된 이미지를 LLM으로 검증한다.
       - 규칙을 지키지 않으면 다시 생성 시도
       - max_generate_tries 안에 모두 실패하면, 마지막 이미지를 그대로 사용한다.
    """

    # 1) 포스터 URL/경로 추출
    image_input = seedream_input.get("image_input") or []
    if not (isinstance(image_input, list) and image_input):
        raise ValueError("seedream_input.image_input 에 참조 포스터 이미지 정보가 없습니다.")

    poster_url = image_input[0].get("url")
    if not poster_url:
        raise ValueError("image_input[0].url 이 비어 있습니다.")

    # 2) 포스터 이미지 로딩 (URL + 로컬 파일 모두 지원)
    img_bytes = _download_image_bytes(poster_url)
    image_file = BytesIO(img_bytes)

    # 3) Replicate에 넘길 공통 input 구성
    prompt = seedream_input.get("prompt", "")
    size = seedream_input.get("size", "custom")
    width = int(seedream_input.get("width", SIGN_PARKING_WIDTH))
    height = int(seedream_input.get("height", SIGN_PARKING_HEIGHT))
    max_images = int(seedream_input.get("max_images", 1))
    aspect_ratio = seedream_input.get("aspect_ratio", "9:16")
    enhance_prompt = bool(seedream_input.get("enhance_prompt", True))
    sequential_image_generation = seedream_input.get(
        "sequential_image_generation", "disabled"
    )

    base_replicate_input = {
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

    model_name = os.getenv("SIGN_PARKING_MODEL", "bytedance/seedream-4")

    # 저장 위치 결정
    if save_dir is not None:
        save_base = Path(save_dir)
    else:
        save_base = _get_sign_parking_save_dir()
    save_base.mkdir(parents=True, exist_ok=True)

    last_validation: Dict[str, Any] | None = None

    # LLM 검증을 포함한 재생성 루프
    for gen_try in range(max_generate_tries):
        # --- Seedream 호출 (모델 에러 시 내부 재시도) ---
        output = None
        last_err: Exception | None = None

        for attempt in range(3):
            try:
                output = replicate.run(model_name, input=base_replicate_input)
                break
            except ModelError as e:
                msg = str(e)
                if "Prediction interrupted" in msg or "code: PA" in msg:
                    last_err = e
                    time.sleep(1.0)
                    continue
                raise RuntimeError(
                    f"Seedream model error during sign parking generation: {e}"
                )
            except Exception as e:
                raise RuntimeError(
                    f"Unexpected error during sign parking generation: {e}"
                )

        if output is None:
            raise RuntimeError(
                f"Seedream model error during sign parking generation after retries: {last_err}"
            )

        if not (isinstance(output, (list, tuple)) and output):
            raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

        file_output = output[0]

        # --- 임시 파일로 저장 ---
        tmp_image_path, tmp_image_filename = _save_image_from_file_output(
            file_output, save_base, prefix=f"{prefix}tmp_"
        )

        # --- LLM으로 규칙 준수 여부 검사 ---
        validation = _validate_sign_parking_image_with_llm(tmp_image_path)
        last_validation = validation

        ok = bool(validation.get("ok", False))
        is_last_try = (gen_try == max_generate_tries - 1)

        if ok or is_last_try:
            # 규칙 통과하거나, 마지막 시도라서 그냥 사용하는 경우
            if not ok:
                print(
                    f"⚠️ sign_parking LLM 검사 실패했지만 "
                    f"max_generate_tries({max_generate_tries}) 소진, 마지막 이미지를 사용합니다: "
                    f"{validation.get('reason', '')}"
                )
            else:
                print(
                    f"✅ sign_parking LLM 검사 통과(gen_try={gen_try+1}/{max_generate_tries})"
                )

            final_filename = "sign_parking.png"
            final_path = save_base / final_filename
            final_path.write_bytes(Path(tmp_image_path).read_bytes())

            return {
                "size": size,
                "width": width,
                "height": height,
                "image_path": str(final_path),
                "image_filename": final_filename,
                "prompt": prompt,
                "festival_name_ko": str(seedream_input.get("festival_name_ko", "")),
                "festival_name_en": str(seedream_input.get("festival_name_en", "")),
                "festival_period_ko": str(seedream_input.get("festival_period_ko", "")),
                "festival_location_ko": str(
                    seedream_input.get("festival_location_ko", "")
                ),
            }

        # 규칙 위반 + 아직 재시도 가능 → 로그만 남기고 다시 생성
        print(
            f"⚠️ sign_parking LLM 검사 실패(gen_try={gen_try+1}/{max_generate_tries}): "
            f"{validation.get('reason', '')}"
        )

    # 이론상 여기까지 안 옴 (위에서 return), 그래도 방어 코드
    raise RuntimeError(
        f"sign_parking image failed LLM validation logic: {last_validation}"
    )


# -------------------------------------------------------------
# 7) editor 저장용 헬퍼 (run_id 기준)
# -------------------------------------------------------------
def run_sign_parking_to_editor(
    run_id: int,
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    editor 용 헬퍼.
    """

    seedream_input = write_sign_parking(
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

    create_result = create_sign_parking(
        seedream_input,
        save_dir=before_image_dir,
        prefix="sign_parking_",
    )

    width = int(create_result.get("width", SIGN_PARKING_WIDTH))
    height = int(create_result.get("height", SIGN_PARKING_HEIGHT))

    image_filename = create_result["image_filename"]
    image_url = f"{EDITOR_STATIC_BASE_URL}/{run_id}/before_image/{image_filename}"

    result: Dict[str, Any] = {
        "type": SIGN_PARKING_TYPE,
        "pro_name": SIGN_PARKING_PRO_NAME,
        "festival_name_en": create_result["festival_name_en"],
        "width": width,
        "height": height,
        "image_url": image_url,
    }

    json_path = before_data_dir / "sign_parking.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


# -------------------------------------------------------------
# 8) CLI 실행용 main
# -------------------------------------------------------------
def main() -> None:
    """
    CLI 실행용 진입점.
    """

    run_id = 10

    poster_image_url = r"C:\final_project\ACC\acc-ai\app\data\mascot\cheonan.png"
    festival_name_ko = "2025 천안흥타령축제"
    festival_period_ko = "2024.09.24 ~ 2024.09.28"
    festival_location_ko = "천안종합운동장 및 천안시 일원"

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

    result = run_sign_parking_to_editor(
        run_id=run_id,
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    editor_root = DATA_ROOT / "editor" / str(run_id)
    json_path = editor_root / "before_data" / "sign_parking.json"
    image_path = editor_root / "before_image" / "sign_parking.png"

    print("✅ sign parking 생성 + editor 저장 완료")
    print("  type             :", result.get("type"))
    print("  pro_name         :", result.get("pro_name"))
    print("  festival_name_en :", result.get("festival_name_en"))
    print("  width x height   :", result.get("width"), "x", result.get("height"))
    print("  image_url        :", result.get("image_url"))
    print("  json_path        :", json_path)
    print("  image_path       :", image_path)


if __name__ == "__main__":
    main()
