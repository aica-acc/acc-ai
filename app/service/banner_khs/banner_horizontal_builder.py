# -*- coding: utf-8 -*-
"""
app/service/banner_khs/banner_horizontal_builder.py

역할
- 참고용 포스터 이미지(URL)와 축제 정보(한글)를 입력받아서
  1) OpenAI LLM이 이미지를 분석하고, 축제명/기간/장소를 영어로 번역한 뒤
     가로형(4:1) 현수막 생성을 위한 영어 프롬프트를 자동 작성
  2) 그 프롬프트와 참고 이미지를 함께 bytedance/seedream-4(Replicate)에 전달해
     4096x1024 가로 현수막 이미지를 생성
  3) 생성된 이미지 파일을 로컬에 저장하고,
     - 이미지 파일 경로/이름
     - 사용된 프롬프트
     - Seedream 입력(JSON 디버그용)
     을 반환한다.

전제 환경변수
- OPENAI_API_KEY              : OpenAI API 키
- REPLICATE_API_TOKEN         : Replicate API 토큰
- BANNER_HORIZONTAL_MODEL     : (선택) 기본값 "bytedance/seedream-4"
- BANNER_HORIZONTAL_SAVE_DIR  : (선택) 기본 "./app/data/banner_horizontal"
- BANNER_LLM_MODEL            : (선택) 기본 "gpt-4o-mini" (또는 원하는 모델명)

주의
- 축제 내용/스타일/색감/질감/표현 방식은 전부 LLM이 포스터+한글 정보를 보고 만든다.
- 파이썬 쪽에서는 4:1 비율, 텍스트 3줄, 가독성, 추가 텍스트 금지 같은 전체 틀만 고정한다.
"""

from __future__ import annotations

import os
import base64
import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Tuple

import requests
import replicate
from openai import OpenAI


# -------------------- 전역 OpenAI 클라이언트 --------------------

_openai_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    """환경변수 OPENAI_API_KEY를 사용해 전역 OpenAI 클라이언트를 하나만 생성."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI()
    return _openai_client


# -------------------- 공통 유틸 --------------------


def _download_image_bytes(poster_image_url: str) -> bytes:
    """
    참고 포스터 이미지를 다운로드해서 raw bytes로 반환.
    - localhost URL이든 외부 URL이든 서버에서 직접 GET 한다.
    - LLM 분석 + Seedream image_input에 같이 재사용한다.
    """
    try:
        resp = requests.get(poster_image_url, timeout=15)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        raise RuntimeError(f"failed to download poster image: {e}")


# -------------------- 프롬프트 조립 --------------------


def _compose_final_prompt(parts: Dict[str, str]) -> str:
    """
    LLM이 JSON으로 준 조각들을 이용해 최종 프롬프트 문자열을 조립한다.
    - 이벤트 설명, 장면/스타일, 텍스트 스타일/제약은 모두 parts에서 가져온다.
    - 코드는 4:1 배너, 텍스트 3줄, 가독성·추가 텍스트 금지만 고정한다.
    """
    title_en = parts.get("title_en", "").strip()
    period_en = parts.get("period_en", "").strip()
    location_en = parts.get("location_en", "").strip()
    short_desc = parts.get("short_event_description_en", "").strip()
    scene_style = parts.get("scene_style_description_en", "").strip()
    text_style = parts.get("text_style_description_en", "").strip()
    negative_text = parts.get("negative_text_constraints_en", "").strip()

    lines: list[str] = []

    # 4:1 비율 + 이벤트 설명 (내용은 전부 LLM이 채운다)
    if short_desc:
        lines.append(f"Ultra-wide 4:1 banner (4096x1024) for {short_desc}.")
    else:
        lines.append("Ultra-wide 4:1 banner (4096x1024).")

    if scene_style:
        lines.append(scene_style)

    # 스타일 상속 + 구성 복사 금지
    lines.append(
        "Use the same color palette and overall visual style as the reference poster, "
        "but create a completely new scene and layout suitable for a wide horizontal banner."
    )
    lines.append("Do NOT copy the exact composition of the reference image.")

    lines.append("")  # 빈 줄

    # 텍스트 3줄 배치
    lines.append(
        "Place three lines of large English text near the center of the banner, "
        "centered horizontally, very big and bold:"
    )
    lines.append("")

    if title_en:
        lines.append(f'"{title_en}"')
    if period_en:
        lines.append(f'"{period_en}"')
    if location_en:
        lines.append(f'"{location_en}"')

    lines.append("")
    lines.append(
        "Use bright high-contrast sans-serif letters that are clearly readable from far away, "
        "with a clean, simple background behind the text so it stands out."
    )

    if text_style:
        lines.append(text_style)
    if negative_text:
        lines.append(negative_text)

    final_prompt = "\n".join(lines).strip()
    return final_prompt


# -------------------- LLM으로 JSON + 프롬프트 생성 --------------------


def _build_prompt_and_use_bytes_with_llm(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
    llm_model: str | None = None,
) -> Tuple[str, bytes]:
    """
    1) 포스터 이미지를 다운로드해서 raw bytes를 얻는다.
    2) 그 bytes를 base64 data URL로 만들어 OpenAI LLM에 보낸다.
    3) LLM이 JSON을 반환하면, 그 조각들로 최종 프롬프트를 조립한다.
    4) (프롬프트, 이미지 bytes) 튜플을 반환한다.
    """
    client = get_openai_client()
    model_name = llm_model or os.getenv("BANNER_LLM_MODEL", "gpt-4o-mini")

    # 1) 이미지 다운로드
    img_bytes = _download_image_bytes(poster_image_url)

    # 2) base64 data URL 변환 (LLM 시각 입력용)
    b64 = base64.b64encode(img_bytes).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"

    # 3) 시스템 프롬프트: JSON 형식 + 구조 설명
    system_prompt = (
        "You are an assistant that prepares structured information for building a prompt "
        "for an image generation model.\n"
        "You will be given:\n"
        " 1) A reference event poster image.\n"
        " 2) The event title, period, and location in Korean.\n\n"
        "Your tasks:\n"
        "- Translate the Korean event title, period, and location into natural English.\n"
        "- Carefully analyze the poster image to understand its visual style "
        "(color palette, lighting, textures, rendering style, main subjects, mood, etc.).\n"
        "- Summarize what kind of event it is and how it feels, based only on the translated text "
        "and the visuals in the poster.\n"
        "- Describe the scene and style in a way that is useful for an image generation model.\n"
        "- Propose how the English event text (title, period, location) should appear in a wide horizontal "
        "4:1 banner so it is very easy to read.\n\n"
        "You must respond as a single JSON object with the following fields (all values are strings):\n"
        "{\n"
        '  "title_en": "...",\n'
        '  "period_en": "...",\n'
        '  "location_en": "...",\n'
        '  "short_event_description_en": "...",\n'
        '  "scene_style_description_en": "...",\n'
        '  "text_style_description_en": "...",\n'
        '  "negative_text_constraints_en": "..." \n'
        "}\n\n"
        "- \"title_en\": English translation of the event title.\n"
        "- \"period_en\": English-style representation of the event period (for example \"2025.08.15 - 08.20\").\n"
        "- \"location_en\": English translation of the event location.\n"
        "- \"short_event_description_en\": a short phrase summarizing the event, such as "
        "\"a summer music festival\" or \"a colorful outdoor event\", based only on the translated text "
        "and the poster. Do NOT mention any specific city/venue names here; those go into location_en.\n"
        "- \"scene_style_description_en\": 1–3 sentences describing the background, atmosphere, main visual "
        "elements and rendering style of the poster (for example, whether it looks like 3D cartoon, flat "
        "illustration, etc.). If the poster does not look photographic, avoid words such as \"photo\", "
        "\"photograph\" or \"realistic photo\".\n"
        "- \"text_style_description_en\": 1–3 sentences describing where and how the English event text "
        "should appear in the banner (which line is biggest, approximate position, contrast, etc.), focusing on "
        "large, bold, high-contrast text that is readable from far away.\n"
        "- \"negative_text_constraints_en\": 1–2 sentences describing what kind of extra text should NOT appear "
        "(for example: no additional slogans, no tiny text, no non-English characters).\n"
        "- Do NOT invent new event names, dates or locations. Use only the given Korean inputs.\n"
        "- All fields must be valid JSON strings. Do NOT include any comments or additional keys.\n"
    )

    user_text = (
        "다음은 축제/이벤트 정보입니다.\n"
        f"- 제목(한국어): {festival_name_ko}\n"
        f"- 기간(한국어): {festival_period_ko}\n"
        f"- 장소(한국어): {festival_location_ko}\n\n"
        "첨부된 이미지는 이 행사를 홍보하는 포스터입니다. 이 이미지를 분석해서, "
        "위 정보를 반영한 가로형(약 4:1 비율) 현수막 이미지를 만들기 위한 "
        "프롬프트를 구성할 정보들을 JSON 형식으로 정리해 주세요."
    )

    resp = client.chat.completions.create(
        model=model_name,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            },
        ],
        temperature=0.4,
    )

    raw_json = resp.choices[0].message.content or "{}"
    try:
        parts = json.loads(raw_json)
    except Exception as e:
        raise RuntimeError(
            f"failed to parse LLM JSON for banner prompt: {e}\nraw: {raw_json!r}"
        )

    final_prompt = _compose_final_prompt(parts)
    return final_prompt, img_bytes


# -------------------- 이미지 저장 유틸 --------------------


def _save_image_from_file_output(file_output: Any, save_dir: Path) -> tuple[str, str]:
    """
    Replicate가 반환하는 FileOutput 또는 URL 문자열을 받아서 디스크에 저장하고,
    (절대경로, 파일명) 튜플을 반환한다.
    """
    save_dir.mkdir(parents=True, exist_ok=True)

    # 기본 확장자는 PNG로 두고, URL에서 추론 가능하면 덮어씀
    ext = ".png"
    url = None

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
    filename = f"banner_horizontal_{timestamp}{ext}"
    filepath = save_dir / filename

    # 데이터 읽기
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


# -------------------- 메인 엔트리: 현수막 생성 --------------------


def generate_horizontal_banner(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
    save_dir: str | Path | None = None,
    llm_model: str | None = None,
    seedream_model: str | None = None,
) -> Dict[str, Any]:
    """
    1) LLM으로 스타일 분석 + 번역 + 프롬프트 조립 (참고 이미지 bytes 함께 사용)
    2) bytedance/seedream-4 에 prompt + image_input(참고 이미지) 함께 전달
    3) 생성된 이미지를 저장하고, 경로/파일명/프롬프트/Seedream 입력 디버그 정보를 반환한다.

    반환 예:
    {
        "image_path": ".../banner_horizontal_20250101_120000.png",
        "image_filename": "banner_horizontal_20250101_120000.png",
        "prompt": "최종 프롬프트 문자열",
        "seedream_input": {
            "size": "custom",
            "width": 4096,
            "height": 1024,
            "prompt": "...",
            "max_images": 1,
            "image_input": ["http://localhost:5000/static/banner/sample_mud.PNG"],
            "aspect_ratio": "4:3",
            "enhance_prompt": true,
            "sequential_image_generation": "disabled"
        }
    }
    """
    # 1. LLM으로 최종 프롬프트 + 참고 이미지 bytes 생성
    prompt, img_bytes = _build_prompt_and_use_bytes_with_llm(
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
        llm_model=llm_model,
    )

    # 2. Seedream-4 input 구성 (실제 replicate용: 파일 객체)
    image_file = BytesIO(img_bytes)
    seedream_input = {
        "size": "custom",
        "width": 4096,
        "height": 1024,
        "prompt": prompt,
        "max_images": 1,
        "image_input": [image_file],
        "aspect_ratio": "4:3",
        "enhance_prompt": True,
        "sequential_image_generation": "disabled",
    }

    # 🔍 디버깅용(JSON 직렬화 가능) 버전 – 응답에 그대로 넣어줄 값
    # 여기에는 실제 파일 대신, 어떤 URL을 참고 이미지로 썼는지 보여준다.
    seedream_input_debug = {
        "size": "custom",
        "width": 4096,
        "height": 1024,
        "prompt": prompt,
        "max_images": 1,
        "image_input": [poster_image_url],
        "aspect_ratio": "4:3",
        "enhance_prompt": True,
        "sequential_image_generation": "disabled",
    }

    # 3. Replicate 호출
    model_name = seedream_model or os.getenv(
        "BANNER_HORIZONTAL_MODEL", "bytedance/seedream-4"
    )
    output = replicate.run(model_name, input=seedream_input)

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]
    save_base = Path(
        save_dir
        or os.getenv("BANNER_HORIZONTAL_SAVE_DIR", "app/data/banner_horizontal")
    ).resolve()

    image_path, image_filename = _save_image_from_file_output(file_output, save_base)

    return {
        "image_path": image_path,
        "image_filename": image_filename,
        "prompt": prompt,
        "seedream_input": seedream_input_debug,
    }
