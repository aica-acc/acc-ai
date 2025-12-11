from pydantic import BaseModel
from typing import Optional

# [Request] Java -> Python
class LivePosterRequest(BaseModel):
    project_id: int                 # p_no
    poster_image_path: str          # 원본 포스터 경로
    
    #  DB(proposal_metadata)에 있는 정보만 사용
    # 입력 안 하면 기본값 사용
    concept_text: str = "A cinematic and dynamic festival poster sequence"
    visual_keywords: str = "high quality, 4k, highly detailed, lighting, atmosphere"


# [Response] Python -> Java (DB live_poster 테이블 컬럼과 1:1)
class LivePosterResponse(BaseModel):
    task_id: str                    # task_id
    file_path: str                  # file_path
    motion_prompt: str              # motion_prompt
    aspect_ratio: Optional[str] = None # 비율 정보 추가 (9:16 등)
    
