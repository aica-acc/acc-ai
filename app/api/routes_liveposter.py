from fastapi import APIRouter, HTTPException
from typing import List
from app.domain.liveposter.liveposter_model import LivePosterRequest, LivePosterResponse
from app.service.liveposter.image_video_generator import generate_live_poster_service

# URL prefix를 "/liveposter"로 설정하여 
# 실제 호출 주소는: http://localhost:8000/liveposter/generate
router = APIRouter(
    prefix="/liveposter",
    tags=["Live Poster Generation"]
)

@router.post("/generate", response_model=List[LivePosterResponse])
async def create_live_poster(request: LivePosterRequest):
    """
    [POST] /liveposter/generate
    Java Backend로부터 요청을 받아 움직이는 포스터(영상)를 생성합니다.
    결과: [9:16 영상, 16:9 영상] 리스트 반환
    """
    try:
        print(f"🚀 [LivePoster] 생성 요청 수신: Project {request.project_id}")
        
        # 서비스 로직 호출 (결과는 리스트 형태 [{}, {}])
        results = await generate_live_poster_service(request)
        
        # 결과 반환 (FastAPI가 자동으로 JSON 리스트로 변환해 줍니다)
        return results
        
    except Exception as e:
        print(f"❌ [LivePoster] API 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=str(e))