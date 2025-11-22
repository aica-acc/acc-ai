# -*- coding: utf-8 -*-
"""
app/service/font_color/bus_font_color_recommend.py

역할
- 버스 외부 광고(road-banner, bus-*) 등에서 생성된 최종 이미지를 보고
  제목/기간/장소(3줄)에 어울리는 font-family 와 색상(hex)을 추천한다.
- 나중에 다른 배너 타입(포스터 등)에서도 재사용할 수 있는 공용 서비스.

입력
- bus_type: "road-banner", "streetlamp-banner" 등 (프롬프트 튜닝용)
- image_path: 로컬에 저장된 최종 배너 이미지 절대경로
- festival_*_placeholder: Seedream에 그려진 라틴 알파벳 / 숫자 플레이스홀더 문자열
- festival_*_base_*: 실제 한글/숫자 텍스트 (원본 축제 정보)

출력(dict)
{
  "festival_font_name_placeholder": "Pretendard",
  "festival_font_period_placeholder": "Suit",
  "festival_font_location_placeholder": "Suit",
  "festival_color_name_placeholder": "#FFFFFF",
  "festival_color_period_placeholder": "#FFE9A3",
  "festival_color_location_placeholder": "#FFE9A3",
}

주의
- 여기서 font-family 문자열은 실제 @font-face 정의와 1:1로 맞아야 한다.
- CSS / 프론트엔드에서 사용할 수 있는 폰트 이름만 FONT_FAMILY_CHOICES 에 넣을 것.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict

from openai import OpenAI

# -------------------------------------------------------------
# 전역 OpenAI 클라이언트
# -------------------------------------------------------------
_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


# -------------------------------------------------------------
# 사용할 font-family 후보 목록
#  - 폰트 실제 @font-face 정의는 별도 CSS / txt 파일에서 관리
#  - 여기서는 font-family 문자열만 사용
# -------------------------------------------------------------
FONT_FAMILY_CHOICES: list[str] = [
    "Pretendard",                # 프리텐다드
    "Paperozi",                  # 페이퍼로지
    "GMarketSans",               # G마켓 산스
    "YeogiOttaeJalnan",          # 여기어때 잘난체
    "Escoredream",               # 에스코어 드림
    "Aggravo",                   # 어그로체
    "PartialSans",               # 파셜산스
    "OngleipParkDahyeon",        # 온글잎 박다현체
    "Presentation",              # 프리젠테이션
    "Suit",                      # 수트
    "Yangjin",                   # 양진체 / HS잔다리체
    "JoseonPalace",              # 조선궁서체
    "GowoonDodum",               # 고운돋움
    "Cafe24Surround",            # 카페24 써라운드
    "IsYun",                     # 이서윤체 / 부크크 명조
    "SchoolSafetyRoundedSmile",  # 학교안심 둥근미소
    "JoseonGulim",               # 조선 굴림체
    "Ria",                       # 리아체
    "SfHambakneun",              # SF함박눈
    "ClipArtKorea",              # 클립아트코리아
    "Isamanru",                  # 이사만루
    "SeoulNotice",               # 서울알림체
    "RoundedFixedsys",           # 둥근모꼴+Fixedsys
    "Yeongwol",                  # 영월체
    "KnpsOdaesan",               # KNPS오대산체
    "ChosunIlboMyungjo",         # 조선일보명조체
    "PyeongchangPeace",          # 평창평화체
    "OngleipKonkon",             # 온글잎 콘콘체
]


# -------------------------------------------------------------
# 유틸: 이미지 파일 → data URL (OpenAI vision 입력용)
# -------------------------------------------------------------
def _image_path_to_data_url(image_path: str) -> str:
    """
    로컬 이미지 파일 경로를 읽어서 base64 data URL 로 변환한다.
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"image not found: {image_path}")

    data = path.read_bytes()

    # 간단 MIME 추론 (확장자 기준)
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext == ".webp":
        mime = "image/webp"
    elif ext == ".png":
        mime = "image/png"
    else:
        # 확장자를 몰라도 대부분 PNG로 처리해도 큰 문제는 없음
        mime = "image/png"

    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _normalize_hex_color(raw: Any, default: str = "#FFFFFF") -> str:
    """
    LLM이 준 문자열을 간단히 검증해서 #RRGGBB 형태로 정규화.
    """
    if not isinstance(raw, str):
        return default

    s = raw.strip()
    if not s:
        return default

    if not s.startswith("#"):
        s = "#" + s

    if len(s) != 7:
        return default

    hex_part = s[1:]
    try:
        int(hex_part, 16)
    except ValueError:
        return default

    return s.upper()


def _safe_get_font_name(raw: Any, fallback: str = "Pretendard") -> str:
    """
    LLM이 준 font-family 가 FONT_FAMILY_CHOICES 안에 없으면
    fallback 으로 치환.
    """
    if not isinstance(raw, str):
        return fallback

    name = raw.strip()
    if not name:
        return fallback

    # 정확히 일치하면 그대로 사용
    if name in FONT_FAMILY_CHOICES:
        return name

    # 대소문자 차이만 있는 경우 보정
    lower_map = {f.lower(): f for f in FONT_FAMILY_CHOICES}
    if name.lower() in lower_map:
        return lower_map[name.lower()]

    # 모르면 fallback
    return fallback


# -------------------------------------------------------------
# 메인 함수
# -------------------------------------------------------------
def recommend_fonts_and_colors_for_bus(
    bus_type: str,
    image_path: str,
    festival_name_placeholder: str,
    festival_period_placeholder: str,
    festival_location_placeholder: str,
    festival_base_name_placeholder: str,
    festival_base_period_placeholder: str,
    festival_base_location_placeholder: str,
) -> Dict[str, Any]:
    """
    최종 배너 이미지와 텍스트 정보를 바탕으로
    제목/기간/장소에 어울리는 font-family 와 글자 색상을 추천한다.

    반환 예:
    {
      "festival_font_name_placeholder": "Pretendard",
      "festival_font_period_placeholder": "Suit",
      "festival_font_location_placeholder": "Suit",
      "festival_color_name_placeholder": "#FFFFFF",
      "festival_color_period_placeholder": "#FFE9A3",
      "festival_color_location_placeholder": "#FFE9A3",
    }
    """
    data_url = _image_path_to_data_url(image_path)
    client = get_openai_client()
    model_name = os.getenv("BANNER_LLM_MODEL", "gpt-4o-mini")

    # ---------- System Prompt ----------
    system_prompt = (
        "You are a Korean outdoor festival bus advertisement and banner design assistant.\n"
        "Your job is to recommend font families and text colors for three text lines:\n"
        "- main title line (festival name)\n"
        "- period line (dates)\n"
        "- location line (venue / area)\n\n"
        "Constraints:\n"
        "- Choose font families ONLY from the provided 'font_family_options' list.\n"
        "- Focus on high legibility from a distance, because these banners are used outdoors.\n"
        "- The main title should be the most eye-catching and bold.\n"
        "- Period and location can be slightly calmer, but still readable and harmonious with the background.\n"
        "- For colors, use hex form like #FFFFFF.\n"
        "- Use high contrast against the actual banner image background.\n"
    )

    # ---------- User Prompt ----------
    font_list_text = ", ".join(FONT_FAMILY_CHOICES)

    meta_json = {
        "bus_type": bus_type,
        "font_family_options": FONT_FAMILY_CHOICES,
        "sections": [
            {
                "id": "name",
                "role": "main_title",
                "placeholder_text": festival_name_placeholder,
                "original_text_ko": festival_base_name_placeholder,
            },
            {
                "id": "period",
                "role": "period",
                "placeholder_text": festival_period_placeholder,
                "original_text_ko": festival_base_period_placeholder,
            },
            {
                "id": "location",
                "role": "location",
                "placeholder_text": festival_location_placeholder,
                "original_text_ko": festival_base_location_placeholder,
            },
        ],
    }

    user_text = (
        "You will see the final generated festival bus exterior advertisement image and metadata.\n"
        "Based on the visual style of the image and the role of each text line, "
        "choose suitable font families and hex text colors for each line.\n\n"
        "Allowed font families (font_family_options):\n"
        f"{font_list_text}\n\n"
        "Important:\n"
        "- Do NOT blindly reuse the same font families for every banner.\n"
        "- For this specific banner, select font families that best match its atmosphere, season, and color palette.\n"
        "- Consider that the main title line should usually be the most eye-catching.\n"
        "- Period and location lines should be readable but may be slightly calmer.\n\n"
        "Return ONLY a JSON object with the following keys:\n"
        '- \"festival_font_name_placeholder\": font-family for the main title line (one of font_family_options)\n'
        '- \"festival_font_period_placeholder\": font-family for the period line (one of font_family_options)\n'
        '- \"festival_font_location_placeholder\": font-family for the location line (one of font_family_options)\n'
        '- \"festival_color_name_placeholder\": hex color for the main title (e.g. \"#FFFFFF\")\n'
        '- \"festival_color_period_placeholder\": hex color for the period line\n'
        '- \"festival_color_location_placeholder\": hex color for the location line\n\n'
        "Metadata (JSON):\n"
        + json.dumps(meta_json, ensure_ascii=False)
    )

    messages: list[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]

    try:
        resp = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=messages,
            # 🔹 다양성을 조금 더 주기 위해 temperature ↑
            temperature=0.7,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"failed to recommend fonts/colors: {e}")

    # --------- 폰트/색 결과 안전하게 파싱 ---------
    font_name = _safe_get_font_name(
        data.get("festival_font_name_placeholder"), fallback="Pretendard"
    )
    font_period = _safe_get_font_name(
        data.get("festival_font_period_placeholder"), fallback="Suit"
    )
    font_location = _safe_get_font_name(
        data.get("festival_font_location_placeholder"), fallback="Suit"
    )

    color_name = _normalize_hex_color(
        data.get("festival_color_name_placeholder"), default="#FFFFFF"
    )
    color_period = _normalize_hex_color(
        data.get("festival_color_period_placeholder"), default="#FFE9A3"
    )
    color_location = _normalize_hex_color(
        data.get("festival_color_location_placeholder"), default="#FFFFFF"
    )

    return {
        "festival_font_name_placeholder": font_name,
        "festival_font_period_placeholder": font_period,
        "festival_font_location_placeholder": font_location,
        "festival_color_name_placeholder": color_name,
        "festival_color_period_placeholder": color_period,
        "festival_color_location_placeholder": color_location,
    }
