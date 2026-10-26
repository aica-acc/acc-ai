from app.core.config import TREND_IMAGE_BASE_URL
import os
from fastapi import APIRouter, Form, HTTPException

# 1. 기존 지역 분석 서비스
from app.service.total_trend.get_region_trend_1year import get_region_trend_1year

# 2. Total Trend 서비스 (구글/유튜브)
from app.service.total_trend.get_google_trends_1year import get_google_trends_1year
# 🔥 [수정] import 경로 변경 (get_youtube_trend -> write_youtube_trend)
from app.service.total_trend.write_youtube_trend import run_youtube_trend

router = APIRouter(prefix="/analyze", tags=["Region Trend Analysis"])

# [신규] 검색량 상승률 계산 함수
def calculate_growth_rate(weekly_data: list, key: str):
    """
    1년 치 데이터에서 '평소 평균' vs '최고점(Peak)'을 비교하여 상승률 계산
    """
    if not weekly_data:
        return 0
    
    values = [item[key] for item in weekly_data if key in item]
    if not values:
        return 0

    # 0이 아닌 값들만으로 평균 계산 (노이즈 제거)
    valid_values = [v for v in values if v > 1] 
    if not valid_values:
        return 0
        
    avg_val = sum(valid_values) / len(valid_values) # 평상시 관심도
    max_val = max(values) # 축제 시즌 최고 관심도
    
    if avg_val == 0: 
        return 0
        
    # 상승률(%) 계산: ((최고점 - 평균) / 평균) * 100
    growth_rate = ((max_val - avg_val) / avg_val) * 100
    return int(growth_rate)

@router.post("/region_trend")
async def analyze_region_trend(
    keyword: str = Form(...),      # 축제명
    host: str = Form(...),         # 지역명
    title: str = Form(...),        
    festivalStartDate: str = Form(...)
):
    # 로컬 이미지 경로 변환 함수
    def convert_local_path_to_url(path: str):
        filename = os.path.basename(path)
        # 실제 배포 환경에 맞춰 도메인/포트 수정 필요 (현재 5000번 가정)
        return f"{TREND_IMAGE_BASE_URL}/{filename}"

    try:
        print(f"🚀 [Region Trend] 분석 시작: {host} (축제: {keyword})")

        # 1️⃣ 네이버 데이터랩 (기본 데이터)
        region_base_result = get_region_trend_1year(
            keyword=keyword, 
            host_name=host, 
            festival_start_date=festivalStartDate
        )
        
        # ★ [추가] 검색량 상승률(폭발력) 분석
        weekly_data = region_base_result.get("region_weekly", [])
        
        festival_growth = calculate_growth_rate(weekly_data, "festival") # 축제 폭발력
        region_growth = calculate_growth_rate(weekly_data, "region")     # 지역 관심도 동반 상승률

        print(f"📈 분석 결과 - 축제 성장률: {festival_growth}%, 지역 성장률: {region_growth}%")

        # 2️⃣ Google Trends
        google_trend = []
        try:
            google_trend = get_google_trends_1year(
                keyword=host,  
                festival_title=title,
                festival_start_date=festivalStartDate,
            )
        except Exception as e:
            print(f"⚠️ Google Trend Error: {e}")

        # 3️⃣ Youtube Trend
        youtube_trend = []
        try:
            # 검색어: "지역명 + 여행" (예: 보령 여행)
            search_query = f"{host} 여행"
            youtube_trend = run_youtube_trend(keyword=search_query)
            
            for item in youtube_trend:
                if item.get("image") and not item["image"].startswith("http"):
                    item["image"] = convert_local_path_to_url(item["image"])
        except Exception as e:
            print(f"⚠️ Youtube Trend Error: {e}")

        # 4️⃣ 결과 반환
        return {
            "status": "success",
            "keyword": keyword,
            "host": host,
            "title": title,
            "festivalStartDate": festivalStartDate,

            # 기존 데이터
            "region_trend": weekly_data,
            "word_cloud": region_base_result.get("word_cloud", []),
            "family": region_base_result.get("family", []),
            "couple": region_base_result.get("couple", []),
            "healing": region_base_result.get("healing", []),

            # 추가 데이터
            "google_trend": google_trend,
            "youtube_trend": youtube_trend,
            
            # ★ [신규] 상승률 데이터
            "growth_stats": {
                "festival_growth": festival_growth, 
                "region_growth": region_growth      
            }
        }
        
    except Exception as e:
        print("❌ Region trend analysis failed:", e)
        return {
            "status": "error", 
            "message": str(e),
            "region_trend": [], 
            "growth_stats": {"festival_growth": 0, "region_growth": 0}
        }