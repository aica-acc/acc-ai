from fastapi import APIRouter
from app.dh.service.festival_plan_service import FestivalService

router = APIRouter(prefix="/festival", tags=["Festival"])

service = FestivalService()

@router.post("/analyze")
def analyze_festival(pdf_path: str, user_theme: str, keywords: list[str], p_name: str):
    """
    축제 기획서 PDF와 유저 입력값을 비교하여 의도 유사도를 반환합니다.
    """
    result = service.analyze(pdf_path, user_theme, keywords, p_name)
    return result

