from app.core.config import TREND_IMAGE_BASE_URL
import os
from fastapi import APIRouter, Form, HTTPException

# 1. 기존 지역 분석 서비스
from app.service.total_trend.get_region_trend_1year import get_region_trend_1year
from app.service.total_trend.trend_inputs import resolve_region_name

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
    keyword: str = Form(...),      # 사용자 키워드 (JSON 배열 문자열일 수 있음)
    host: str = Form(...),         # 기획서 '주최' (비어 있거나 기관명일 수 있음)
    title: str = Form(...),
    festivalStartDate: str = Form(...),
    location: str = Form(""),      # 기획서 '장소' (지역 이름 추정에 사용)
):
    # 로컬 이미지 경로 변환 함수
    def convert_local_path_to_url(path: str):
        filename = os.path.basename(path)
        # 실제 배포 환경에 맞춰 도메인/포트 수정 필요 (현재 5000번 가정)
        return f"{TREND_IMAGE_BASE_URL}/{filename}"

    try:
        # 주최가 '정보 없음'이거나 기관명이면 축제명·장소로 시·군 이름을 정한다
        region = resolve_region_name(host, location, title)
        print(f"🚀 [Region Trend] 분석 시작: {host} → 지역 {region} (축제: {keyword})")
        notices = []

        # 1️⃣ 네이버 데이터랩 (기본 데이터)
        region_base_result = get_region_trend_1year(
            keyword=keyword,
            host_name=region,
            festival_start_date=festivalStartDate,
            title=title,
        )

        # ★ [추가] 검색량 상승률(폭발력) 분석 (예시 곡선이면 계산하지 않는다)
        weekly_data = region_base_result.get("region_weekly", [])
        simulated = region_base_result.get("simulated", False)
        if simulated:
            festival_growth = region_growth = None
            notices.append(f"실제 검색 데이터가 부족해 예시 곡선을 표시합니다 ({region_base_result.get('simulated_reason')}).")
        else:
            festival_growth = calculate_growth_rate(weekly_data, "festival") # 축제 폭발력
            region_growth = calculate_growth_rate(weekly_data, "region")     # 지역 관심도 동반 상승률
        # 키워드별 미니 그래프(D-6~D-0)는 실제 검색량이 아니라 점수로 만든 예시다
        notices.append("키워드별 미니 그래프는 관심도 점수로 만든 예시입니다.")

        print(f"📈 분석 결과 - 축제 성장률: {festival_growth}%, 지역 성장률: {region_growth}%")

        # 2️⃣ Google Trends
        google_trend = []
        try:
            google_trend = get_google_trends_1year(
                keyword=region,
                festival_title=title,
                festival_start_date=festivalStartDate,
            )
        except Exception as e:
            print(f"⚠️ Google Trend Error: {e}")
        if not google_trend:
            notices.append("구글 트렌드를 일시적으로 조회하지 못했습니다.")

        # 3️⃣ Youtube Trend
        youtube_trend = []
        try:
            # 검색어: "지역명 + 여행" (예: 보령 여행)
            search_query = f"{region} 여행"
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

            # 분석에 실제로 쓴 값과 신뢰도 표시 (화면이 예시 데이터임을 알릴 수 있게)
            "region_name": region,
            "region_trend_simulated": simulated,
            "search_terms": region_base_result.get("search_terms"),
            "search_window": region_base_result.get("search_window"),
            "keyword_trend_simulated": True,
            "notices": notices,

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
        # 예전에는 빈 데이터를 200 으로 돌려줘 백엔드가 성공으로 보고 크레딧도 환불하지 않았다 (#31)
        print("❌ Region trend analysis failed:", e)
        raise HTTPException(status_code=502, detail="region trend analysis failed")