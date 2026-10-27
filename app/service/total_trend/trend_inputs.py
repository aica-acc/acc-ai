"""
트렌드 분석 입력 정리: 검색어, 지역 이름, 조회 기간.

예전 문제
  - 키워드가 JSON 배열 문자열('["태화강", "봄꽃"]') 통째로 네이버 검색어에 들어가 검색량이 0 에 가까웠다.
  - 지역 이름을 기획서 '주최' 칸에서 그대로 가져와, 주최가 '정보 없음'이면 '정보 없음 여행'을 검색했다.
  - 조회 기간이 항상 '오늘부터 1년 전'이라 2023년 축제도 2025~2026 검색량을 봤다.
"""
import datetime
import json
import os
import re
from typing import List

from openai import OpenAI

from app.core.config import OPENAI_TEXT_MODEL

_EMPTY = {"", "정보 없음", "정보없음", "없음", "미정", "-", "n/a", "none", "null"}
_ORG_HINTS = ("㈜", "(주)", "방송", "재단", "위원회", "협회", "주식회사", "추진위", "공사", "센터")


def parse_keywords(keyword) -> List[str]:
    """키워드가 JSON 배열 문자열로 와도 개별 키워드 목록으로 푼다."""
    if isinstance(keyword, list):
        items = keyword
    else:
        text = (keyword or "").strip()
        try:
            items = json.loads(text) if text.startswith("[") else [text]
        except ValueError:
            items = text.strip("[]").replace('"', "").split(",")
    return [str(k).strip() for k in items if str(k).strip()]


def clean_title(title: str) -> str:
    """'2023 태화강 국가정원 봄꽃축제', '제7회 담양산타축제' → 연도·회차를 뺀 축제명"""
    t = re.sub(r"^\s*(19|20)\d{2}\s*", "", title or "")
    t = re.sub(r"^\s*제?\s*\d+\s*회\s*", "", t)
    return t.strip()


def festival_terms(keyword, title: str = "", limit: int = 5) -> List[str]:
    """네이버 데이터랩 '축제' 그룹 검색어: 정리한 축제명 + 사용자 키워드 앞 3개 (중복 제거)"""
    terms = [clean_title(title)] + parse_keywords(keyword)[:3]
    return list(dict.fromkeys(t for t in terms if t))[:limit]


def resolve_region_name(host: str, location: str = "", title: str = "") -> str:
    """
    지역 트렌드에 쓸 시·군 이름.
    주최가 비었거나('정보 없음') 회사·방송사 같은 기관명이면, 축제명·장소·주최를 보고 가벼운 모델로 시·군 이름만 뽑는다.
    """
    host = (host or "").strip()
    if host.lower() not in _EMPTY and not any(h in host for h in _ORG_HINTS) and len(host) <= 12:
        return re.sub(r"(특별시|광역시|특별자치시|특별자치도|시청|군청|구청)$", "", host) or host
    try:
        res = OpenAI(api_key=os.getenv("OPENAI_API_KEY")).chat.completions.create(
            model=OPENAI_TEXT_MODEL,
            temperature=0,
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": (
                    "다음 축제가 열리는 지역의 시·군 이름만 한 단어로 답하세요 (예: 울산, 담양, 보령). 모르면 '모름'.\n"
                    f"축제명: {title}\n장소: {location}\n주최: {host}"
                ),
            }],
        )
        words = (res.choices[0].message.content or "").strip().split()
        name = words[0].strip(".,") if words else ""
        if name and name != "모름":
            return name
    except Exception as e:
        print(f"[RegionTrend] 지역명 추출 실패: {e}")
    loc = (location or "").split()
    return loc[0] if loc else (clean_title(title).split() or [""])[0]


def search_window(festival_start_date: str):
    """검색량 조회 기간(1년). 지난 축제면 축제 2개월 뒤까지, 아니면 오늘까지."""
    today = datetime.date.today()
    end = today
    try:
        fd = datetime.datetime.strptime((festival_start_date or "")[:10], "%Y-%m-%d").date()
        if fd < today - datetime.timedelta(days=30):
            end = min(today, fd + datetime.timedelta(days=60))
    except ValueError:
        pass
    start = max(end - datetime.timedelta(days=360), datetime.date(2016, 1, 1))  # 데이터랩 제공 시작
    return start, end
