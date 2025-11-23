from pydantic import BaseModel
from typing import Optional

# [Request] Java -> Python (mood 삭제)
class LivePosterRequest(BaseModel):
    project_id: int                 # p_no
    poster_image_path: str          # 원본 포스터 경로
    
    #  DB(proposal_metadata)에 있는 정보만 사용
    concept_text: str               # concept_description (기획 의도)
    visual_keywords: str            # visual_keywords (시각적 키워드)

# [Response] Python -> Java (DB live_poster 테이블 컬럼과 1:1)
class LivePosterResponse(BaseModel):
    task_id: str                    # task_id
    file_path: str                  # file_path
    motion_prompt: str              # motion_prompt