# app/router/trend_total_router.py

from app.core.config import TREND_IMAGE_BASE_URL
import os
import json
from fastapi import APIRouter, Form, HTTPException

# === 너가 올린 파일 import (이미 존재) ===
from app.service.total_trend.get_google_trends_1year import get_google_trends_1year
from app.service.total_trend.get_google_trends_keyword import get_google_related_from_llm
from app.service.total_trend.get_naver_datalab_1year import get_naver_datalab_1year
from app.service.total_trend.write_youtube_trend import run_youtube_trend
from app.service.total_trend.get_youtube_trend import run_youtube_search

router = APIRouter(prefix="/analyze", tags=["Total Trend Analysis"])

@router.post("/total_trend")
async def analyze_total_trend(
    keyword: str = Form(...),
    title: str = Form(...),
    festivalStartDate: str = Form(...),
):
    
    def convert_local_path_to_url(path: str):
        filename = os.path.basename(path)
        return f"{TREND_IMAGE_BASE_URL}/{filename}"

    try:
        # ================================
        # 1) GOOGLE TRENDS (1년)
        # ================================
        google_trend = get_google_trends_1year(
            keyword=keyword,
            festival_title=title,
            festival_start_date=festivalStartDate,
        )

        # ================================
        # 2) GOOGLE 연관검색어
        # ================================
        related_keywords = get_google_related_from_llm(
            keyword=keyword,
            festival_title=title,
            festival_start_date=festivalStartDate,
        )

        # ================================
        # 3) NAVER DATALAB
        # ================================
        naver_weekly = get_naver_datalab_1year(
            keyword=keyword,
            festival_title=title,
            festival_start_date=festivalStartDate,
        )

        # ================================
        # 4) YOUTUBE SEARCH (short + long)
        # ================================
        run_youtube_search(keyword=keyword)

        # ================================
        # 5) YOUTUBE TREND
        # ================================
        
        youtube_trend = run_youtube_trend(keyword=keyword)
        

         # 🧩 이미지 경로 로컬 → URL 변환
        for item in youtube_trend:
            if item.get("image"):
                item["image"] = convert_local_path_to_url(item["image"])

        # ================================
        # 5) 최종 결과 패키징
        # ================================
        return {
            "status": "success",
            "keyword": keyword,
            "title": title,
            "festivalStartDate": festivalStartDate,
            "google_trend": google_trend,
            "related_keywords": related_keywords,
            "naver_datalab": naver_weekly,
            "youtube_trend": youtube_trend,
        }

    except Exception as e:
        print("❌ FastAPI total trend error:", e)
        raise HTTPException(500, "Total trend analysis failed")

