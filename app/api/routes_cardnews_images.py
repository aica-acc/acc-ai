
from fastapi import APIRouter, Query
from app.tools.cardnews.image_loader import download_cardnews_images
from app.service.cardnews.cardnews_score_service import hybrid_cardnews_score

router = APIRouter(prefix="/festival", tags=["Festival"])

@router.get("/cardnews")
async def get_cardnews(
    festival_name: str = Query(...),
    region: str = Query(...),
    year: int = Query(...),
    theme: str | None = Query(None, description="기획의도/테마(없으면 자동배치모드)"),
    category: str = Query("전체"),
    limit_images: int = Query(5)
):
    """
    🎯 FastAPI → SpringBoot 연동용 라우터
    - 카드뉴스 이미지 수집
    - 하이브리드 점수화 수행(CLIP + LLM)
    - SpringBoot가 DB에 저장하기 좋은 JSON 형태로 반환
    """

    # 카테고리별 검색 쿼리 정의
    if category == "전체":
        categories = {
            "지도": f"{festival_name} 카드뉴스 지도 site:instagram.com",
            "부스소개": f"{festival_name} 카드뉴스 부스소개 site:instagram.com",
            "행사일정": f"{festival_name} 카드뉴스 행사일정 site:instagram.com",
            "축제개요": f"{festival_name} 카드뉴스 축제개요 site:instagram.com",
        }
    else:
        categories = {category: f"{festival_name} 카드뉴스 {category} site:instagram.com"}

    response = []

    for cat, query in categories.items():
        try:
            # 1. 이미지 수집
            records = await download_cardnews_images(
                category=cat,
                query=query,
                festival_name=festival_name,
                region=region,
                year=year,
                limit_images=limit_images
            )

            # 2. 점수화 + JSON 변환
            scored_items = []
            for rec in records:
                score = hybrid_cardnews_score(
                    rec["file_path"],
                    text_prompt=theme  # theme 없으면 자동배치 모드
                )

                scored_items.append({
                    "file_path": rec["file_path"],
                    "original_url": rec["original_url"],
                    "category": cat,
                    "festival_name": festival_name,
                    "region": region,
                    "year": year,
                    "score": score.model_dump()
                })

            response.append({
                "category": cat,
                "images": scored_items
            })

        except Exception as e:
            response.append({
                "category": cat,
                "error": str(e)
            })

    return {
        "festival_name": festival_name,
        "region": region,
        "year": year,
        "theme": theme,
        "results": response
    }