# -*- coding: utf-8 -*-
"""
app/service/banner_khs/make_road_banner.py

도로(4:1) 가로 현수막용 Seedream 입력/프롬프트 생성 + 생성 이미지 저장 모듈.

역할
- 참고용 포스터 이미지(URL)와 축제 정보(한글)를 입력받아서
  1) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  2) 포스터 이미지를 시각적으로 분석해서 "축제 씬 묘사"를 영어로 만든 뒤
  3) 한글 자리수에 맞춘 플레이스홀더 텍스트(라틴 알파벳 시퀀스)를 사용해서
     4:1 도로용 현수막 프롬프트를 조립한다. (write_road_banner)
  4) 해당 JSON을 받아 Replicate(Seedream)를 호출해 실제 이미지를 생성하고 저장한다. (create_road_banner)

특징
- 나중에 편집툴에서 한글로 교체할 수 있도록,
  실제로 그려지는 텍스트는
    * 축제명  : 한글 자릿수만큼 A, B, C, ... (A부터 시작하는 대문자 시퀀스)
    * 축제기간: 숫자/기호는 그대로, 한글만 라틴 문자 시퀀스(기본 C부터)
    * 축제장소: 한글 자릿수만큼 B, C, D, ... (B부터 시작하는 대문자 시퀀스)
  로 마스킹해서 넘긴다.
- 축제명이 가장 크고(배너 너비의 절반 정도 차지), 기간/장소는 그보다 작게 나오도록 프롬프트에 명시한다.

전제 환경변수
- OPENAI_API_KEY          : OpenAI API 키
- BANNER_LLM_MODEL        : (선택) 기본값 "gpt-4o-mini"
- ROAD_BANNER_MODEL       : (선택) 기본값 "bytedance/seedream-4"
- ROAD_BANNER_SAVE_DIR    : (선택) 기본값 "app/data/road_banner"
"""

from __future__ import annotations

import os
import json
import base64
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

import requests
import replicate
from openai import OpenAI
import time
from replicate.exceptions import ModelError


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
# 한글 포함 여부 + 자리수 플레이스홀더 유틸
# -------------------------------------------------------------
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _contains_hangul(text: str) -> bool:
    """문자열에 한글(가-힣)이 하나라도 포함되어 있는지 확인."""
    for ch in str(text or ""):
        if "가" <= ch <= "힣":
            return True
    return False


def _build_placeholder_from_hangul(text: str, mask_char: str) -> str:
    """
    문자열에서 한글(가-힣)만 라틴 대문자 시퀀스로 치환하고,
    숫자/영문/공백/기호 등은 그대로 둔다.

    - mask_char: 시퀀스를 시작할 기준 문자.
      예) mask_char='A' → A,B,C,D,E,F,...
          mask_char='B' → B,C,D,E,F,G,...

    예:
      text="2025 보령머드축제", mask_char='A' → "2025 ABCDEF"
      text="보령시 대천해수욕장 일대", mask_char='B' → "BCDE FGHIJKLM NO"
    """
    if not text:
        return ""

    mask_char = (mask_char or "A").upper()
    try:
        start_idx = _ALPHABET.index(mask_char)
    except ValueError:
        start_idx = 0

    idx = start_idx
    result: list[str] = []

    for ch in str(text):
        if "가" <= ch <= "힣":
            # 한글 하나당 서로 다른 대문자로 매핑
            result.append(_ALPHABET[idx % len(_ALPHABET)])
            idx += 1
        else:
            # 숫자/기호/공백 등은 그대로 유지
            result.append(ch)

    return "".join(result).strip()


def _download_image_bytes(url: str) -> bytes:
    """
    포스터 이미지를 다운로드해서 raw bytes로 반환.
    (LLM 시각 입력 또는 Seedream용)
    """
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        raise RuntimeError(f"failed to download poster image: {e}")


# -------------------------------------------------------------
# 1) 한글 축제 정보 → 영어 번역 (씬 묘사용)
#     - 실제 텍스트 라인에 쓰지는 않고,
#       포스터 씬 묘사를 자연스럽게 만들기 위한 용도로만 사용
# -------------------------------------------------------------
def _translate_festival_ko_to_en(
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, str]:
    """
    한글로 들어온 축제명/기간/장소를
    현수막용 배경/씬 묘사를 위한 영어 표현으로 번역한다.

    규칙:
    - 각 필드(제목/기간/장소)별로 한글이 하나라도 포함되어 있으면 번역 대상.
    - 해당 필드에 한글이 전혀 없으면 (숫자/영어/기호만 있으면) 원문을 그대로 유지.
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
                        'Return ONLY a JSON object with the keys "name_en", "period_en", "location_en".\n\n'
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
# 2) 포스터 이미지 + 번역된 정보 → 씬 묘사 JSON
# -------------------------------------------------------------
def _build_scene_phrase_from_poster(
    poster_image_url: str,
    festival_name_en: str,
    festival_period_en: str,
    festival_location_en: str,
) -> Dict[str, str]:
    """
    포스터 이미지와 영어 축제 정보를 보고,
    - base_scene_en       : "Ultra-wide 4:1 illustration of ..." 뒷부분에 들어갈 핵심 장면 설명
    - details_phrase_en   : 장면 안의 주요 오브젝트/군중/동작 등을 한 문장으로 요약
    을 LLM에게서 JSON으로 받아온다.
    """
    client = get_openai_client()
    model_name = os.getenv("BANNER_LLM_MODEL", "gpt-4o-mini")

    # 포스터 이미지를 base64 data URL로 변환 (OpenAI 시각 입력용)
    img_bytes = _download_image_bytes(poster_image_url)
    b64 = base64.b64encode(img_bytes).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"

    system_prompt = (
        "You are helping to design an ultra-wide roadside festival banner.\n"
        "You will see a reference festival poster image and simple English metadata about the event.\n"
        "Analyze the image and text and respond with a single JSON object:\n"
        "{\n"
        '  "base_scene_en": "...",\n'
        '  "details_phrase_en": "..."\n'
        "}\n\n"
        "- base_scene_en: a short English phrase that can complete the sentence "
        '"Ultra-wide 4:1 illustration of ...". Do NOT mention aspect ratio, layout, or text placement. '
        'Example: "a vibrant summer mud festival by the beach at sunset".\n'
        "- details_phrase_en: one concise sentence describing the key subjects, objects, and motion in the scene, "
        "such as crowds, stages, cars, mud splashes, rides, snow, lights, etc. "
        "This should describe what is happening visually, not how the text is placed.\n"
        "- Do NOT start base_scene_en with phrases like \"Ultra-wide\" or \"4:1\"; just describe the scene itself.\n"
        "- Do NOT invent a new event name, date, or location: rely only on the given metadata."
    )

    user_text = (
        "Event metadata (English):\n"
        f"- title: {festival_name_en}\n"
        f"- period: {festival_period_en}\n"
        f"- location: {festival_location_en}\n\n"
        "Use this information together with the attached poster image to describe the overall scene and style."
    )

    try:
        resp = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            temperature=0.4,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        base_scene_en = str(data.get("base_scene_en", "")).strip()
        details_phrase_en = str(data.get("details_phrase_en", "")).strip()
    except Exception as e:
        print(f"[make_road_banner._build_scene_phrase_from_poster] failed: {e}")
        base_scene_en = ""
        details_phrase_en = ""

    def _norm(s: str) -> str:
        # 줄바꿈/연속 공백 제거 → Seedream이 \n 못 알아듣는 문제 피하기
        return " ".join(str(s or "").split())

    base_scene_en = _norm(base_scene_en)
    details_phrase_en = _norm(details_phrase_en)

    # fallback: 그래도 비어있으면 대체 문구
    if not base_scene_en:
        base_scene_en = _norm(
            f"a vibrant outdoor festival inspired by {festival_name_en}".strip()
        )

    # 혹시 LLM이 "Ultra-wide 4:1 illustration of ..." 까지 같이 써버린 경우 제거
    lower = base_scene_en.lower()
    for prefix in [
        "ultra-wide 4:1 illustration of",
        "ultra wide 4:1 illustration of",
        "ultra-wide illustration of",
        "wide 4:1 illustration of",
    ]:
        if lower.startswith(prefix):
            base_scene_en = base_scene_en[len(prefix):].lstrip(" ,.-")
            break

    if not details_phrase_en:
        details_phrase_en = _norm(
            "with a lively crowd, dynamic motion, and rich lighting, digital art style"
        )

    return {
        "base_scene_en": base_scene_en,
        "details_phrase_en": details_phrase_en,
    }


# -------------------------------------------------------------
# 3) 영어 씬 묘사 + 플레이스홀더 텍스트 → 최종 프롬프트 문자열
# -------------------------------------------------------------


def _build_road_banner_prompt_en(
    name_text: str,
    period_text: str,
    location_text: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    def _norm(s: str) -> str:
        return " ".join(str(s or "").split())

    base_scene_en = _norm(base_scene_en)
    details_phrase_en = _norm(details_phrase_en)
    name_text = _norm(name_text)
    period_text = _norm(period_text)
    location_text = _norm(location_text)

    prompt = (
        f"Ultra-wide 4:1 illustration of {base_scene_en}, "
        "using the attached poster image only as reference for bright colors, lighting and atmosphere "
        f"but creating a completely new scene with {details_phrase_en}. "
        "In the exact center of the banner, stack exactly three lines of text, all perfectly center-aligned horizontally. "
        f"On the middle line, write \"{name_text}\" in extremely large, ultra-bold sans-serif letters, "
        "the largest text in the entire image and clearly readable from a very long distance. "
        f"On the top line, directly above the title, write \"{period_text}\" in smaller bold sans-serif letters. "
        f"On the bottom line, directly below the title, write \"{location_text}\" in a size slightly smaller than the top line. "
        "All three lines must be drawn in the foremost visual layer, clearly on top of every background element, "
        "character, object, and effect in the scene, and nothing may overlap, cover, or cut through any part of the letters. "
        "Draw exactly these three lines of text once each. Do not draw any second copy, shadow copy, reflection, "
        "mirrored copy, outline-only copy, blurred copy, or partial copy of any of this text anywhere else in the image, "
        "including on the ground, sky, water, buildings, decorations, or interface elements. "
        "Do not add any other text at all: no extra words, labels, dates, numbers, logos, watermarks, or UI elements "
        "beyond these three lines. "
        "Do not place the text on any banner, signboard, panel, box, frame, ribbon, or physical board; "
        "draw only clean floating letters directly over the background. "
        "The quotation marks in this prompt are for instruction only; do not draw quotation marks in the final image."
    )

    return prompt.strip()




# -------------------------------------------------------------
# 4) write_road_banner: Seedream 입력 JSON 생성 (+ 플레이스홀더 포함)
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
      ],
      "festival_name_placeholder": "2025 ABCDEF",
      "festival_period_placeholder": "2025.08.15 ~ 2025.08.20",
      "festival_location_placeholder": "BCDE FGHIJKLM NO",
      "festival_base_name_placeholder": "제 11회 해운대 빛 축제",
      "festival_base_period_placeholder": "2024.12.14 ~ 2025.02.02",
      "festival_base_location_placeholder": "부산 해운대 일대"
    }
    """

    # 1) 한글 축제 정보 → 영어 번역 (씬 묘사용)
    translated = _translate_festival_ko_to_en(
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    name_en = translated["name_en"]
    period_en = translated["period_en"]
    location_en = translated["location_en"]

    # 2) 자리수 맞춘 플레이스홀더 + 원본 한글 텍스트 보존
    placeholders: Dict[str, str] = {
        # 축제명: A부터 시작하는 시퀀스
        "festival_name_placeholder": _build_placeholder_from_hangul(
            festival_name_ko, "A"
        ),
        # 축제기간: 숫자/기호는 그대로, 한글만 C부터 시작하는 시퀀스
        "festival_period_placeholder": _build_placeholder_from_hangul(
            festival_period_ko, "C"
        ),
        # 축제장소: B부터 시작하는 시퀀스
        "festival_location_placeholder": _build_placeholder_from_hangul(
            festival_location_ko, "B"
        ),
        # 🔹 원본 한글 텍스트도 그대로 같이 넣어줌 (나중에 폰트/색상 추천용)
        "festival_base_name_placeholder": str(festival_name_ko or ""),
        "festival_base_period_placeholder": str(festival_period_ko or ""),
        "festival_base_location_placeholder": str(festival_location_ko or ""),
    }

    # 3) 포스터 이미지 분석 → 씬 묘사 얻기
    scene_info = _build_scene_phrase_from_poster(
        poster_image_url=poster_image_url,
        festival_name_en=name_en,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )

    # 4) 최종 프롬프트 조립
    prompt = _build_road_banner_prompt_en(
        name_text=placeholders["festival_name_placeholder"],
        # 기간 플레이스홀더가 비어 있으면 번역된/원본 period_en 사용
        period_text=placeholders["festival_period_placeholder"] or period_en,
        location_text=placeholders["festival_location_placeholder"],
        base_scene_en=scene_info["base_scene_en"],
        details_phrase_en=scene_info["details_phrase_en"],
    )

    # 5) Seedream / Replicate 입력 JSON 구성
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": 4096,
        "height": 1024,
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
    }

    # 🔹 플레이스홀더 + 원본 한글도 같이 포함
    seedream_input.update(placeholders)

    return seedream_input


# -------------------------------------------------------------
# 5) 이미지 생성용 유틸 (Seedream/Replicate 호출)
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
# 6) create_road_banner: Seedream JSON → Replicate 호출 → 이미지 저장
#     + 플레이스홀더까지 같이 반환
# -------------------------------------------------------------

def create_road_banner(seedream_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    /road-banner/write 에서 만든 Seedream 입력 JSON을 그대로 받아
    1) image_input 에서 포스터 URL을 추출하고,
    2) 그 이미지를 다운로드해 파일 객체로 만든 뒤,
    3) Replicate(bytedance/seedream-4)에 prompt + image_input과 함께 전달해
       실제 4:1 가로 현수막 이미지를 생성하고,
    4) 생성된 이미지를 로컬에 저장한다.

    반환:
    {
      "image_path": "...",
      "image_filename": "...",
      "prompt": "...",
      "festival_name_placeholder": "...",
      "festival_period_placeholder": "...",
      "festival_location_placeholder": "...",
      "festival_base_name_placeholder": "...",
      "festival_base_period_placeholder": "...",
      "festival_base_location_placeholder": "..."
    }
    """

    # 🔹 입력 JSON에서 플레이스홀더 + 원본 한글 그대로 꺼냄
    festival_name_placeholder = str(seedream_input.get("festival_name_placeholder", ""))
    festival_period_placeholder = str(
        seedream_input.get("festival_period_placeholder", "")
    )
    festival_location_placeholder = str(
        seedream_input.get("festival_location_placeholder", "")
    )

    festival_base_name_placeholder = str(
        seedream_input.get("festival_base_name_placeholder", "")
    )
    festival_base_period_placeholder = str(
        seedream_input.get("festival_base_period_placeholder", "")
    )
    festival_base_location_placeholder = str(
        seedream_input.get("festival_base_location_placeholder", "")
    )

    # 1) 포스터 URL 추출
    poster_url = _extract_poster_url_from_input(seedream_input)
    if not poster_url:
        raise ValueError("seedream_input.image_input 에 참조 포스터 이미지 URL이 없습니다.")

    # 2) 포스터 이미지 다운로드 → 파일 객체
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

    # 🔁 Seedream / Replicate 일시 오류(PA 등)에 대비한 재시도 로직
    output = None
    last_err: Exception | None = None

    for attempt in range(3):  # 최대 3번까지 시도
        try:
            output = replicate.run(model_name, input=replicate_input)
            break  # 성공하면 루프 탈출
        except ModelError as e:
            msg = str(e)
            # Prediction interrupted; please retry (code: PA) 같은 일시 오류만 재시도
            if "Prediction interrupted" in msg or "code: PA" in msg:
                last_err = e
                time.sleep(1.0)
                continue
            # 그 외 ModelError는 그대로 넘김
            raise RuntimeError(
                f"Seedream model error during road banner generation: {e}"
            )
        except Exception as e:
            # 네트워크 등 다른 예외는 바로 실패
            raise RuntimeError(
                f"Unexpected error during road banner generation: {e}"
            )

    # 3번 모두 실패한 경우
    if output is None:
        raise RuntimeError(
            f"Seedream model error during road banner generation after retries: {last_err}"
        )

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]

    save_base = Path(os.getenv("ROAD_BANNER_SAVE_DIR", "app/data/road_banner")).resolve()
    image_path, image_filename = _save_image_from_file_output(
        file_output, save_base, prefix="road_banner_"
    )

    # 🔹 여기서 플레이스홀더 + 원본 한글까지 같이 반환
    return {
        "image_path": image_path,
        "image_filename": image_filename,
        "prompt": prompt,
        "festival_name_placeholder": festival_name_placeholder,
        "festival_period_placeholder": festival_period_placeholder,
        "festival_location_placeholder": festival_location_placeholder,
        "festival_base_name_placeholder": festival_base_name_placeholder,
        "festival_base_period_placeholder": festival_base_period_placeholder,
        "festival_base_location_placeholder": festival_base_location_placeholder,
    }


