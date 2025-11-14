# app/service/banner/banner_trend_analysis/service_banner_image_trend_analysis.py
# -*- coding: utf-8 -*-
"""
/banner/analyze-image 에서 사용할 축제 배너 추천 서비스

- 입력: p_name, user_theme, keywords(list[str])
- 내부 데이터 소스: app/data/festivals_with_banners.json
- 출력:
    {
      "related_festivals": [... 최대 5개 ...],
      "latest_festivals":  [... 최대 5개 ...]
    }
"""

from __future__ import annotations

from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime
import json

# app 디렉토리 기준으로 data/festivals_with_banners.json 찾기
APP_DIR = Path(__file__).resolve().parents[3]  # .../app/service/banner/banner_trend_analysis/ -> app
DATA_PATH = APP_DIR / "data" / "festivals_with_banners.json"


def _load_all_festivals() -> List[Dict[str, Any]]:
    """
    festivals_with_banners.json을 읽어서 리스트[dict]로 반환.
    파일이 없거나 형식이 이상하면 빈 리스트 반환.
    """
    if not DATA_PATH.exists():
        # 파일 못 찾으면 그냥 빈 리스트
        return []

    try:
        raw = DATA_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    return [f for f in data if isinstance(f, dict)]


def _parse_date(value: str) -> datetime:
    """
    "YYYY-MM-DD" 혹은 "YYYY.MM.DD" 정도만 단순 지원.
    실패하면 아주 과거 날짜로 취급.
    """
    if not value:
        return datetime.min

    for fmt in ("%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    return datetime.min


def _score_festival(f: Dict[str, Any], p_name: str, user_theme: str, keywords: List[str]) -> int:
    """
    축제 1개에 대한 간단한 연관도 점수 계산.

    - 축제 이름/태그/지역 문자열 안에
      p_name / user_theme 토큰 / keywords 가 얼마나 겹치는지로 가중치를 준다.
    """
    name_ko = f.get("name_ko", "")
    tags = f.get("tags", [])
    region = f.get("region", "")

    # 축제 쪽 텍스트를 하나로 합치기
    festival_text = " ".join(
        [
            str(name_ko),
            " ".join(str(t) for t in tags),
            str(region),
        ]
    )

    # 입력 쪽 토큰 모으기
    terms: set[str] = set()

    # keywords 그대로
    for kw in keywords:
        kw = kw.strip()
        if kw:
            terms.add(kw)

    # p_name / user_theme를 공백 기준으로 쪼개서 토큰으로 사용
    for raw in (p_name, user_theme):
        for token in str(raw).replace(",", " ").split():
            token = token.strip()
            if token:
                terms.add(token)

    # 실제 매칭 점수 계산
    score = 0
    for t in terms:
        if t and t in festival_text:
            score += 1

    return score


def analyze_banner_image_trend(
    p_name: str,
    user_theme: str,
    keywords: List[str],
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    - related_festivals: 입력과 연관도 점수가 높은 축제 상위 top_k개
    - latest_festivals: 시작일 기준 최신 축제 top_k개
    """
    all_fests = _load_all_festivals()

    if not all_fests:
        # 데이터 없으면 그냥 빈 결과
        return {
            "related_festivals": [],
            "latest_festivals": [],
        }

    # 1) 연관도 점수 계산
    for f in all_fests:
        f["_score"] = _score_festival(f, p_name, user_theme, keywords)

    # 점수 + 시작일 기준 정렬 (점수 > 최근 시작일 우선)
    sorted_by_score = sorted(
        all_fests,
        key=lambda f: (
            f.get("_score", 0),
            _parse_date(f.get("start_date", "")),
        ),
        reverse=True,
    )

    related: List[Dict[str, Any]] = []
    for f in sorted_by_score:
        if len(related) >= top_k:
            break
        if f.get("_score", 0) <= 0:
            # 한 개도 안 맞으면 '연관 축제'로 보긴 애매해서 제외
            continue

        related.append(
            {
                "festival_id": f.get("id"),
                "festival_name": f.get("name_ko"),
                "banner_image_url": f.get("banner_image_url"),
                "banner_image_description": f.get("banner_image_description"),
                "start_date": f.get("start_date"),
                "end_date": f.get("end_date"),
                "region": f.get("region"),
                "score": f.get("_score", 0),
            }
        )

    # 2) 최신 축제 top_k (날짜 기준)
    sorted_by_date = sorted(
        all_fests,
        key=lambda f: _parse_date(f.get("start_date", "")),
        reverse=True,
    )

    latest: List[Dict[str, Any]] = []
    for f in sorted_by_date[:top_k]:
        latest.append(
            {
                "festival_id": f.get("id"),
                "festival_name": f.get("name_ko"),
                "banner_image_url": f.get("banner_image_url"),
                "banner_image_description": f.get("banner_image_description"),
                "start_date": f.get("start_date"),
                "end_date": f.get("end_date"),
                "region": f.get("region"),
            }
        )

    return {
        "related_festivals": related,
        "latest_festivals": latest,
    }
