# -*- coding: utf-8 -*-
"""
app/service/banner_khs/make_road_banner.py

도로(4:1) 가로 현수막용 Seedream 입력/프롬프트 생성 + 생성 이미지 저장 모듈.

역할
- 참고용 포스터 이미지(URL)와 축제 정보(한글)를 입력받아서
  1) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  2) 포스터 이미지와 어울리는 4:1 가로 현수막을 만들도록 지시하는 영어 프롬프트를 작성한 뒤
  3) bytedance/seedream-4(또는 호환 모델)에 줄 입력 JSON(dict)을 만들어 반환한다. (write_road_banner)
  4) 해당 JSON을 받아 Replicate(Seedream)를 호출해 실제 이미지를 생성하고 저장한다. (create_road_banner)

전제 환경변수
- OPENAI_API_KEY          : OpenAI API 키
- BANNER_LLM_MODEL        : (선택) 기본값 "gpt-4o-mini"
- ROAD_BANNER_MODEL       : (선택) 기본값 "bytedance/seedream-4"
- ROAD_BANNER_SAVE_DIR    : (선택) 기본값 "app/data/road_banner"
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

import requests
import replicate
from openai import OpenAI


# -------------------------------------------------------------
# 전역 OpenAI 클라이언트
# -------------------------------------------------------------
_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    """환경변수 OPENAI_API_KEY를 사용해 전역 OpenAI 클라이언트를 하나만 생성."""
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


# -------------------------------------------------------------
# 한글 포함 여부 유틸
# -------------------------------------------------------------
def _contains_hangul(text: str) -> bool:
    """문자열에 한글(가-힣)이 하나라도 포함되어 있는지 확인."""
    for ch in str(text):
        if "가" <= ch <= "힣":
            return True
    return False


# -------------------------------------------------------------
# 1) 한글 축제 정보 → 영어 번역 (필드별로 한글이 있을 때만 번역)
# -------------------------------------------------------------
def _translate_festival_ko_to_en(
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, str]:
    """
    한글로 들어온 축제명/기간/장소를
    현수막용으로 자연스러운 영어 표현으로 번역한다.

    규칙:
    - 각 필드(제목/기간/장소)별로 한글이 하나라도 포함되어 있으면 번역 대상.
    - 해당 필드에 한글이 전혀 없으면 (숫자/영어/기호만 있으면) 원문을 그대로 유지한다.
    """

    # 원본 문자열
    name_src = festival_name_ko or ""
    period_src = festival_period_ko or ""
    location_src = festival_location_ko or ""

    # 필드별 한글 포함 여부
    has_ko_name = _contains_hangul(name_src)
    has_ko_period = _contains_hangul(period_src)
    has_ko_location = _contains_hangul(location_src)

    # 셋 다 한글이 없으면 → LLM 호출 없이 그대로 반환
    if not (has_ko_name or has_ko_period or has_ko_location):
        return {
            "name_en": name_src,
            "period_en": period_src,
            "location_en": location_src,
        }

    # 여기서부터는 최소 한 필드에 한글이 있는 경우 → LLM 번역 사용
    client = get_openai_client()
    model_name = os.getenv("BANNER_LLM_MODEL", "gpt-4o-mini")

    system_msg = (
        "You are a translation assistant for outdoor festival banners. "
        "Translate Korean festival information into concise, natural English "
        "suitable for large roadside banners."
    )

    user_payload = {
        "festival_name_ko": name_src,
        "festival_period_ko": period_src,
        "festival_location_ko": location_src,
    }

    try:
        resp = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": system_msg,
                },
                {
                    "role": "user",
                    "content": (
                        "Translate the following Korean festival information into English. "
                        "Return ONLY a JSON object with the keys "
                        "\"name_en\", \"period_en\", \"location_en\".\n\n"
                        + json.dumps(user_payload, ensure_ascii=False)
                    ),
                },
            ],
            temperature=0.2,
        )

        data = json.loads(resp.choices[0].message.content)

        # LLM이 제안한 번역 값
        name_candidate = str(data.get("name_en", name_src)).strip()
        period_candidate = str(data.get("period_en", period_src)).strip()
        location_candidate = str(data.get("location_en", location_src)).strip()

        # 필드별 규칙 적용
        # 1) 한글이 있는 필드 → 번역 결과가 비어있지 않으면 번역 사용, 아니면 원문
        # 2) 한글이 없는 필드 → 무조건 원문 유지
        if has_ko_name and name_candidate:
            name_en = name_candidate
        else:
            name_en = name_src

        if has_ko_period and period_candidate:
            period_en = period_candidate
        else:
            period_en = period_src

        if has_ko_location and location_candidate:
            location_en = location_candidate
        else:
            location_en = location_src

        return {
            "name_en": name_en,
            "period_en": period_en,
            "location_en": location_en,
        }

    except Exception as e:
        # 번역이 완전히 실패하면 그냥 원문 그대로 반환
        print(f"[make_road_banner._translate_festival_ko_to_en] failed: {e}")
        return {
            "name_en": name_src,
            "period_en": period_src,
            "location_en": location_src,
        }


# -------------------------------------------------------------
# 2) 영어 정보 → 최종 프롬프트 문자열 (축제 씬 스타일, 3줄 텍스트 강제)
# -------------------------------------------------------------
def _build_road_banner_prompt_en(
    name_en: str,
    period_en: str,
    location_en: str,
) -> str:
    """
    번역된 영어 축제 정보(제목/기간/장소)를 사용해
    4:1 도로용 현수막 생성을 위한 영어 프롬프트를 만든다.

    - boryung_horizontal_banner1~3 같은 "영화 스틸컷 느낌"의 축제 씬을 노린다.
    - 텍스트는 정확히 3줄, 각각 딱 1번만 사용.
      1) 맨 위: 기간 (중간 크기)
      2) 가운데: 축제명 (가장 크고 두꺼운 메인 제목)
      3) 맨 아래: 장소 (조금 더 작은 보조 라인)
    """

    name_en = (name_en or "").strip()
    period_en = (period_en or "").strip()
    location_en = (location_en or "").strip()

    lower_name = name_en.lower()
    lower_loc = location_en.lower()
    is_mud_festival = "mud" in lower_name or "mud" in lower_loc

    lines: list[str] = []

    # 4:1 비율 + 용도 설명
    lines.append(
        "Ultra-wide roadside festival banner, 4:1 ratio (4096x1024), high-resolution illustration for large outdoor printing."
    )

    # 참고 포스터 이미지 사용 지시
    lines.append(
        "Use the attached reference poster image ONLY as inspiration for the overall color palette, lighting, mood, and visual style."
    )
    lines.append(
        "Design a completely new wide horizontal composition that feels consistent with the reference, but do NOT copy the exact layout, characters, logos, or typography."
    )

    # ---- 배경: 축제 씬 스타일 (머드 축제면 조금 더 구체적으로) ----
    if is_mud_festival:
        lines.append(
            "Show a vibrant summer mud festival by the beach at sunset: a warm pink–orange sky, people of all ages covered in mud, big splashes of mud in the foreground, and a lively crowd, stage, tents and buildings stretching across the horizon."
        )
    else:
        lines.append(
            "Show a vibrant outdoor festival at sunset: a warm colorful sky, a lively crowd, a main stage with lights, tents and buildings stretching across the horizon."
        )

    lines.append(
        "The overall style should look like a polished 3D animated movie frame: clean shapes, rich lighting, high detail but not photorealistic."
    )
    lines.append(
        "Arrange characters, crowd and scenery across the full width of the banner, but keep a broad, softer, lower-detail band through the center so that the text overlay stays extremely easy to read from far away."
    )

    # ---- 텍스트 영역: 정확히 3줄, 각각 1번만 ----
    lines.append(
        "In this central band, create exactly three separate lines of English text, centered horizontally."
    )
    lines.append(
        f'The three lines must appear from top to bottom exactly as follows: '
        f'first line (medium size) "{period_en}", second line (very large and bold, the biggest text in the entire banner) "{name_en}", '
        f'third line (slightly smaller than the first line) "{location_en}".'
    )
    lines.append(
        "Each of these phrases must appear once and only once. Do NOT repeat them, do NOT split them into multiple lines, and do NOT change their order."
    )
    lines.append(
        "Do NOT add any other words, slogans, extra numbers, or non-English characters anywhere in the image."
    )

    # ---- 글자 스타일 & 가독성 ----
    lines.append(
        "Use clean, bold, high-contrast sans-serif Latin lettering. The digits in the date must be crisp, clear and easy to read, with no distortion, smearing or glitch effects."
    )
    lines.append(
        "Ensure very strong contrast between the text and the background, and avoid placing bright objects, characters or busy patterns directly behind the letters."
    )
    lines.append(
        "The quotation marks in this prompt are for explanation only; do NOT draw any quotation marks in the image."
    )

    return "\n".join(lines).strip()


# -------------------------------------------------------------
# 3) write_road_banner: Seedream 입력 JSON 생성
# -------------------------------------------------------------
def write_road_banner(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    도로(4:1) 가로 현수막용 Seedream 입력 JSON을 생성한다.

    입력:
        poster_image_url    : 참고용 포스터 이미지 URL
        festival_name_ko    : 축제명 (한글)
        festival_period_ko  : 축제 기간 (한글 또는 숫자/영문)
        festival_location_ko: 축제 장소 (한글 또는 영문)

    출력 (Seedream / Replicate 등에 바로 넣을 수 있는 dict):

    {
      "size": "custom",
      "width": 4096,
      "height": 1024,
      "prompt": "<영문 프롬프트 문자열>",
      "max_images": 1,
      "aspect_ratio": "match_input_image",
      "enhance_prompt": true,
      "sequential_image_generation": "disabled",
      "image_input": [
        {
          "type": "image_url",
          "url": "<poster_image_url>"
        }
      ]
    }
    """

    # 1) 한글 축제 정보 → 영어 번역 (필드별 한글 여부에 따라 번역/유지)
    translated = _translate_festival_ko_to_en(
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    # 2) 4:1 가로 현수막용 프롬프트 생성
    prompt = _build_road_banner_prompt_en(
        name_en=translated["name_en"],
        period_en=translated["period_en"],
        location_en=translated["location_en"],
    )

    # 3) Seedream / Replicate 입력 JSON 구성
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": 4096,
        "height": 1024,
        "prompt": prompt,
        "max_images": 1,
        # Seedream 설정에 따라 다를 수 있음. 사용 중인 스펙에 맞게 조정 가능.
        "aspect_ratio": "match_input_image",
        "enhance_prompt": True,
        "sequential_image_generation": "disabled",
        # 참고 포스터 이미지를 그대로 넘김 (모델이 색감/스타일 참고용으로 사용)
        "image_input": [
            {
                "type": "image_url",
                "url": poster_image_url,
            }
        ],
    }

    return seedream_input


# -------------------------------------------------------------
# 4) 이미지 생성용 유틸 (Seedream/Replicate 호출)
# -------------------------------------------------------------
def _extract_poster_url_from_input(seedream_input: Dict[str, Any]) -> str:
    """
    seedream_input["image_input"] 에서 실제 포스터 URL을 찾아낸다.
    지원 형태:
      - [{"type": "image_url", "url": "..."}]
      - ["http://..."]
      - {"url": "..."}
    """
    image_input = seedream_input.get("image_input")

    # 리스트 형태
    if isinstance(image_input, list) and image_input:
        first = image_input[0]
        if isinstance(first, dict):
            return first.get("url") or first.get("image_url") or ""
        if isinstance(first, str):
            return first
    # dict 형태
    if isinstance(image_input, dict):
        return image_input.get("url") or image_input.get("image_url") or ""

    return ""


def _save_image_from_file_output(
    file_output: Any, save_dir: Path, prefix: str = "road_banner_"
) -> tuple[str, str]:
    """
    Replicate가 반환하는 FileOutput 또는 URL 문자열을 받아서 디스크에 저장하고,
    (절대경로, 파일명) 튜플을 반환한다.
    """
    save_dir.mkdir(parents=True, exist_ok=True)

    ext = ".png"
    url: str | None = None

    # FileOutput 객체인 경우
    if hasattr(file_output, "url") and callable(file_output.url):
        try:
            url = file_output.url()
        except Exception:
            url = None
    elif isinstance(file_output, str):
        url = file_output

    if isinstance(url, str):
        name_part = url.split("?")[0].rstrip("/").split("/")[-1]
        if "." in name_part:
            ext = "." + name_part.split(".")[-1]

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}{timestamp}{ext}"
    filepath = save_dir / filename

    # 실제 바이너리 읽기
    if hasattr(file_output, "read") and callable(file_output.read):
        data: bytes = file_output.read()
    elif isinstance(url, str):
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.content
    else:
        raise RuntimeError(f"unsupported file_output type: {type(file_output)!r}")

    with filepath.open("wb") as f:
        f.write(data)

    return str(filepath), filename


# -------------------------------------------------------------
# 5) create_road_banner: Seedream JSON → Replicate 호출 → 이미지 저장
# -------------------------------------------------------------
def create_road_banner(seedream_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    /road-banner/write 에서 만든 Seedream 입력 JSON을 그대로 받아
    1) image_input 에서 포스터 URL을 추출하고,
    2) 그 이미지를 다운로드해 파일 객체로 만든 뒤,
    3) Replicate(bytedance/seedream-4)에 prompt + image_input과 함께 전달해
       실제 4:1 가로 현수막 이미지를 생성하고,
    4) 생성된 이미지를 로컬에 저장한다.
    """

    # 1) 포스터 URL 추출
    poster_url = _extract_poster_url_from_input(seedream_input)
    if not poster_url:
        raise ValueError("seedream_input.image_input 에 참조 포스터 이미지 URL이 없습니다.")

    # 2) 포스터 이미지 다운로드 → 바이너리 → 파일 객체
    resp = requests.get(poster_url, timeout=30)
    resp.raise_for_status()
    img_bytes = resp.content
    image_file = BytesIO(img_bytes)

    # 3) Replicate에 넘길 input 구성
    prompt = seedream_input.get("prompt", "")
    size = seedream_input.get("size", "custom")
    width = int(seedream_input.get("width", 4096))
    height = int(seedream_input.get("height", 1024))
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
        "image_input": [image_file],  # Replicate에는 실제 파일 객체로 전달
        "aspect_ratio": aspect_ratio,
        "enhance_prompt": enhance_prompt,
        "sequential_image_generation": sequential_image_generation,
    }

    model_name = os.getenv("ROAD_BANNER_MODEL", "bytedance/seedream-4")
    output = replicate.run(model_name, input=replicate_input)

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]

    save_base = Path(os.getenv("ROAD_BANNER_SAVE_DIR", "app/data/road_banner")).resolve()
    image_path, image_filename = _save_image_from_file_output(
        file_output, save_base, prefix="road_banner_"
    )

    return {
        "image_path": image_path,
        "image_filename": image_filename,
        "prompt": prompt,
    }
