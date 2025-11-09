from fastapi import APIRouter, Form
from app.service.festival.festival_plan_service import FestivalService

router = APIRouter(prefix="/festival", tags=["Festival"])

service = FestivalService()

@router.post("/analyze")
async def analyze_festival(
    pdf_path: str = Form(...),
    user_theme: str = Form(...),
    keywords: str = Form(""),
    p_name: str = Form(...)
):
    """
    축제 기획서 PDF와 유저 입력값을 비교하여 의도 유사도를 반환합니다.
    """
    # keywords: "봄,꽃,가족" -> ["봄", "꽃", "가족"]
    keywords_list = [k.strip() for k in keywords.split(",") if k.strip()]

    result = service.analyze(pdf_path, user_theme, keywords_list, p_name)
    return result
