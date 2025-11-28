# -*- coding: utf-8 -*-
"""
app/service/banner_khs/make_road_banner.py

도로(4:1) 가로 현수막용 Seedream 입력/프롬프트 생성 + 생성 이미지 저장 + editor 저장 모듈.

역할
- 참고용 포스터 이미지(URL 또는 로컬 파일 경로)와 축제 정보(한글)를 입력받아서
  1) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  2) 포스터 이미지를 시각적으로 분석해서 "축제 씬 묘사"를 영어로 만든 뒤
  3) 한글 자리수에 맞춘 플레이스홀더 텍스트(라틴 알파벳 시퀀스)를 사용해서
     4:1 도로용 현수막 프롬프트를 조립한다. (write_road_banner)
  4) 해당 JSON을 받아 Replicate(Seedream)를 호출해 실제 이미지를 생성하고 저장한다. (create_road_banner)
  5) run_road_banner_to_editor(...) 로 run_id 기준 editor 폴더에 JSON/이미지 사본을 저장한다.
  6) python make_road_banner.py 로 단독 실행할 수 있다.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List
import requests
import replicate
from openai import OpenAI
from dotenv import load_dotenv
from replicate.exceptions import ModelError

# -------------------------------------------------------------
# 프로젝트 루트 및 .env 로딩 + sys.path 설정
# -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / "app" / "data"  # ✅ app/data 아래로만 쓰기/읽기

# 배너 고정 스펙
BANNER_TYPE = "road_banner"
BANNER_PRO_NAME = "도로용 현수막"
BANNER_WIDTH = 4096
BANNER_HEIGHT = 1024

# C:\final_project\ACC\acc-ai\.env 로딩
env_path = PROJECT_ROOT / ".env"
load_dotenv(env_path)

# app 패키지 import를 위해 루트를 sys.path에 추가
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
# 한글 판별 + 자리수 플레이스홀더 유틸
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


# -------------------------------------------------------------
# 포스터 이미지 로딩 (URL + 로컬 파일 모두 지원)
# -------------------------------------------------------------
def _download_image_bytes(path_or_url: str) -> bytes:
    """
    path_or_url 이
      - http://, https:// 로 시작하면 → HTTP GET
      - 그 외 → 로컬 파일 경로로 간주 (상대경로면 PROJECT_ROOT 기준)
    """
    s = str(path_or_url or "").strip()
    if not s:
        raise RuntimeError("poster image path/url is empty")

    # HTTP(S)인 경우
    if s.startswith("http://") or s.startswith("https://"):
        try:
            resp = requests.get(s, timeout=20)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            raise RuntimeError(f"failed to download poster image: {e}")

    # 로컬 파일인 경우
    p = Path(s)
    if not p.is_absolute():
        p = PROJECT_ROOT / p  # ✅ 항상 프로젝트 루트 기준

    if not p.is_file():
        raise RuntimeError(f"poster image file not found: {p}")

    return p.read_bytes()


# -------------------------------------------------------------
# 1) 한글 축제 정보 → 영어 번역 (씬 묘사용)
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
        '  \"base_scene_en\": \"...\",\n'
        '  \"details_phrase_en\": \"...\"\n'
        "}\n\n"
        "- base_scene_en: a short English phrase that can complete the sentence "
        "\"Ultra-wide 4:1 illustration of ...\". Do NOT mention aspect ratio, layout, or text placement. "
        'Example: \"a vibrant summer mud festival by the beach at sunset\".\n'
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
        f"Ultra-wide 4:1 festival banner illustration of {base_scene_en}, "
        "using the attached poster image only as reference for bright colors, lighting and atmosphere "
        f"but creating a completely new scene with {details_phrase_en}. "
        "Place three lines of text near the horizontal center of the banner, all perfectly center-aligned. "
        f"On the middle line, write \"{name_text}\" in extremely large, ultra-bold sans-serif letters, "
        "the largest text in the entire image and clearly readable from a very long distance. "
        f"On the top line, directly above the title, write \"{period_text}\" in smaller bold sans-serif letters, "
        "but still clearly readable from far away. "
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

    # f"초광각 4:1 축제 배너 일러스트 {base_scene_en},"
    # "첨부된 포스터 이미지를 밝은 색상, 조명 및 분위기에만 참고할 수 있습니다."
    # f"하지만 {details_phrase_en}으로 완전히 새로운 장면을 만들고 있습니다."
    # 배너의 가로 중앙 근처에 세 줄의 텍스트를 배치하고, 모두 완벽하게 중앙에 정렬합니다
    # f"가운데 줄에 \\"{name_text}\"를 매우 크고 굵은 산세리프 문자로 씁니다,"
    # "전체 이미지에서 가장 큰 텍스트이며 매우 먼 거리에서도 명확하게 읽을 수 있습니다."
    # f"제목 바로 위의 맨 위 줄에 \\"{period_text}\"를 작은 굵은 산세리프 문자로 씁니다,"
    # "하지만 여전히 멀리서도 분명히 읽을 수 있습니다."
    # f"아래쪽 줄에는 제목 바로 아래에 \\"{location_text}\\"라고 맨 위 줄보다 약간 작은 크기로 적습니다."
    # "세 줄 모두 모든 배경 요소 위에 명확하게 가장 앞쪽 시각적 층에 그려야 합니다,"
    # "장면에서 등장인물, 객체, 효과는 글자의 어떤 부분도 겹치거나 덮거나 자를 수 없습니다."
    # "이 세 줄의 텍스트를 각각 한 번씩 정확하게 그리세요. 두 번째 복사본, 그림자 복사본, 반사를 그리지 마세요,"
    # "이미지의 다른 부분에 있는 이 텍스트의 mirrored 사본, 개요 전용 사본, 흐릿한 사본 또는 부분 사본"
    # 지상, 하늘, 물, 건물, 장식 또는 인터페이스 요소를 포함하여
    # "다른 텍스트는 전혀 추가하지 마세요: 단어, 라벨, 날짜, 숫자, 로고, 워터마크 또는 UI 요소는 추가하지 마세요."
    # "이 세 줄을 beyond."
    # "글을 배너, 간판, 패널, 상자, 프레임, 리본 또는 물리적 보드에 배치하지 마십시오;"
    # 배경 바로 위에 깨끗한 떠다니는 글자만 그립니다
    # "이 프롬프트의 따옴표는 지시용이므로 최종 이미지에 따옴표를 그리지 마세요."
    
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
        "festival_name_placeholder": _build_placeholder_from_hangul(
            festival_name_ko, "A"
        ),
        "festival_period_placeholder": _build_placeholder_from_hangul(
            festival_period_ko, "C"
        ),
        "festival_location_placeholder": _build_placeholder_from_hangul(
            festival_location_ko, "B"
        ),
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
        period_text=placeholders["festival_period_placeholder"] or period_en,
        location_text=placeholders["festival_location_placeholder"],
        base_scene_en=scene_info["base_scene_en"],
        details_phrase_en=scene_info["details_phrase_en"],
    )

    # 5) Seedream / Replicate 입력 JSON 구성
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": BANNER_WIDTH,
        "height": BANNER_HEIGHT,
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
    seedream_input.update(placeholders)
    return seedream_input


# -------------------------------------------------------------
# 5) 이미지 생성용 유틸 (Seedream/Replicate 호출)
# -------------------------------------------------------------
def _extract_poster_url_from_input(seedream_input: Dict[str, Any]) -> str:
    """
    seedream_input["image_input"] 에서 실제 포스터 URL 또는 로컬 경로를 찾아낸다.
    """
    image_input = seedream_input.get("image_input")

    if isinstance(image_input, list) and image_input:
        first = image_input[0]
        if isinstance(first, dict):
            return first.get("url") or first.get("image_url") or ""
        if isinstance(first, str):
            return first
    if isinstance(image_input, dict):
        return image_input.get("url") or image_input.get("image_url") or ""

    return ""


def _get_road_banner_save_dir() -> Path:
    """
    ROAD_BANNER_SAVE_DIR 환경변수가 있으면:
      - 절대경로면 그대로 사용
      - 상대경로면 PROJECT_ROOT 기준으로 사용
    없으면:
      - PROJECT_ROOT/app/data/road_banner 사용
    """
    env_dir = os.getenv("ROAD_BANNER_SAVE_DIR")
    if env_dir:
        p = Path(env_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    return DATA_ROOT / "road_banner"


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

    # ✅ 여기부터 파일명 고정 로직
    base_name = (prefix or "road_banner").rstrip("_")
    filename = f"{base_name}{ext}"
    filepath = save_dir / filename

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
# -------------------------------------------------------------
def create_road_banner(
    seedream_input: Dict[str, Any],
    save_dir: Path | None = None,
    prefix: str = "road_banner_",
) -> Dict[str, Any]:
    """
    write_road_banner(...) 에서 만든 Seedream JSON을 받아
    Seedream-4(Replicate)로 이미지를 생성하고 저장한다.

    save_dir 가 주어지면 그 디렉터리에 저장하고,
    없으면 ROAD_BANNER_SAVE_DIR / app/data/road_banner 에 저장한다.
    """

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

    poster_url = _extract_poster_url_from_input(seedream_input)
    if not poster_url:
        raise ValueError("seedream_input.image_input 에 참조 포스터 이미지 URL이 없습니다.")

    # URL이든 로컬 파일이든 동일하게 처리
    img_bytes = _download_image_bytes(poster_url)
    image_file = BytesIO(img_bytes)

    prompt = seedream_input.get("prompt", "")
    size = seedream_input.get("size", "custom")
    width = int(seedream_input.get("width", BANNER_WIDTH))
    height = int(seedream_input.get("height", BANNER_HEIGHT))
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

    model_name = os.getenv("ROAD_BANNER_MODEL", "bytedance/seedream-4")

    output = None
    last_err: Exception | None = None

    for _ in range(3):
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
                f"Seedream model error during road banner generation: {e}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error during road banner generation: {e}"
            )

    if output is None:
        raise RuntimeError(
            f"Seedream model error during road banner generation after retries: {last_err}"
        )

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]

    # ✅ save_dir 가 있으면 그쪽으로 바로 저장, 없으면 기존 road_banner 디렉터리 사용
    if save_dir is None:
        save_base = _get_road_banner_save_dir()
    else:
        save_base = Path(save_dir)

    image_path, image_filename = _save_image_from_file_output(
        file_output, save_base, prefix=prefix,
    )

    return {
        "size": size,
        "width": width,
        "height": height,
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


# -------------------------------------------------------------
# 7) editor 저장용 헬퍼 + main
# -------------------------------------------------------------
def _get_project_root() -> Path:
    """
    acc-ai 루트 디렉터리를 반환한다.
    """
    return PROJECT_ROOT


def run_road_banner_to_editor(
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
      1) write_road_banner(...) 로 Seedream 입력용 seedream_input 생성
      2) create_road_banner(..., save_dir=before_image_dir) 로
         실제 도로 배너 이미지를 생성하고,
         app/data/editor/<run_id>/before_image/road_banner.png 로 저장한다.
      3) 배너 타입, 한글 축제 정보, 배너 크기만을 포함한
         최소 결과 JSON을 구성하여
         app/data/editor/<run_id>/before_data/road_banner.json 에 저장한다.

    반환:
      {
        "type": "road_banner",
        "pro_name": "도로용 현수막",
        "festival_name_ko": ...,
        "festival_period_ko": ...,
        "festival_location_ko": ...,
        "width": 4096,
        "height": 1024
      }
    """

    # 1) Seedream 입력 생성
    seedream_input = write_road_banner(
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    # 2) editor 디렉터리 준비  ✅ app/data/editor/<run_id>/...
    editor_root = DATA_ROOT / "editor" / str(run_id)
    before_data_dir = editor_root / "before_data"
    before_image_dir = editor_root / "before_image"
    before_data_dir.mkdir(parents=True, exist_ok=True)
    before_image_dir.mkdir(parents=True, exist_ok=True)

    # 3) 실제 배너 이미지 생성 (저장 위치를 before_image_dir 로 바로 지정)
    create_result = create_road_banner(
        seedream_input,
        save_dir=before_image_dir,
        prefix="road_banner_",
    )

    # 4) 최종 결과 JSON (API/백엔드에서 사용할 최소 정보 형태)
    result: Dict[str, Any] = {
        "type": BANNER_TYPE,
        "pro_name": BANNER_PRO_NAME,
        "festival_name_ko": festival_name_ko,
        "festival_period_ko": festival_period_ko,
        "festival_location_ko": festival_location_ko,
        "width": int(create_result.get("width", BANNER_WIDTH)),
        "height": int(create_result.get("height", BANNER_HEIGHT)),
    }

    # 5) before_data 밑에 JSON 저장 (파일명 고정)
    json_path = before_data_dir / "road_banner.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def main() -> None:
    """
    CLI 실행용 진입점.

    ✅ 콘솔에서:
        python make_road_banner.py

    를 실행하면, 아래에 적어둔 입력값으로
    - 도로 배너 생성 (Seedream)
    - app/data/editor/<run_id>/before_data, before_image 저장
    까지 한 번에 수행한다.
    """

    # 1) 여기 값만 네가 원하는 걸로 수정해서 쓰면 됨
    run_id = 10  # 에디터 실행 번호 (폴더 이름에도 사용됨)

    # 로컬 포스터 파일 경로 (PROJECT_ROOT/app/data/banner/...)
    # 필요하면 아래 한 줄을 str(DATA_ROOT / "banner" / "busan.png") 로 바꿔도 됨
    poster_image_url = r"C:\final_project\ACC\acc-ai\app\data\banner\goheung.png"
    festival_name_ko = "제 15회 고흥 우주항공 축제"
    festival_period_ko = "2025.05.03 ~ 2025.05.06"
    festival_location_ko = "고흥군 봉래면 나로우주센터 일원"

    # 2) 혹시라도 비어 있으면 바로 알려주기
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
    result = run_road_banner_to_editor(
        run_id=run_id,
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    editor_root = DATA_ROOT / "editor" / str(run_id)
    json_path = editor_root / "before_data" / "road_banner.json"
    image_path = editor_root / "before_image" / "road_banner.png"

    print("✅ road banner 생성 + editor 저장 완료")
    print("  type              :", result.get("type"))
    print("  pro_name          :", result.get("pro_name"))
    print("  festival_name_ko  :", result.get("festival_name_ko"))
    print("  festival_period_ko:", result.get("festival_period_ko"))
    print("  festival_location_ko:", result.get("festival_location_ko"))
    print("  width x height    :", result.get("width"), "x", result.get("height"))
    print("  json_path         :", json_path)
    print("  image_path        :", image_path)


if __name__ == "__main__":
    main()
