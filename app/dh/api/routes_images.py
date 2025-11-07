
from fastapi import APIRouter, Query
from dh.tools.image_loader import download_cardnews_images
import asyncio

router = APIRouter(prefix="/festival", tags=["Festival"])

@router.get("/cardnews")
async def get_cardnews(
    festival_name: str = Query(..., description="축제명 (예: 태화강 봄꽃축제)"),
    region: str = Query(..., description="지역 (예: 울산)"),
    year: int = Query(..., description="연도 (예: 2023)"),
    category: str = Query("전체", description="카드뉴스 카테고리 (지도, 부스소개 등)"),
    limit_images: int = Query(5, description="가져올 이미지 개수 제한")
):
    """
    ✅ FastAPI 라우터
    축제명과 지역을 기준으로 카드뉴스 데이터를 수집합니다.
    oEmbed 지원 시 슬라이드형까지 포함하고,
    미지원 시 SerpApi 썸네일만 수집합니다.
    """

    # 카테고리 목록 정의
    if category == "전체":
        categories = {
            "지도": f"{festival_name} 카드뉴스 지도 site:instagram.com",
            "부스소개": f"{festival_name} 카드뉴스 부스소개 site:instagram.com",
            "행사일정": f"{festival_name} 카드뉴스 행사일정 site:instagram.com",
            "축제개요": f"{festival_name} 카드뉴스 축제개요 site:instagram.com",
        }
    else:
        categories = {category: f"{festival_name} 카드뉴스 {category} site:instagram.com"}

    result_summary = {}

    for cat, query in categories.items():
        try:
            records = await download_cardnews_images(
                category=cat,
                query=query,
                festival_name=festival_name,
                region=region,
                year=year,
                limit_images=limit_images
            )
            result_summary[cat] = {"status": "success", "count": len(records)}
        except Exception as e:
            result_summary[cat] = {"status": "error", "message": str(e)}

    return {
        "festival_name": festival_name,
        "region": region,
        "year": year,
        "results": result_summary
    }
