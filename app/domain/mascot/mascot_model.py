from pydantic import BaseModel
from typing import Dict, Any, List, Optional

# 프롬프트 생성 스키마
# 스프링 서버 요청 값
class MascotPromptRequest(BaseModel):
    member_no: str
    project_no: int
    metadata: Dict[str, Any]     # DB에서 가져온 분석/기획 정보
    user_input: Dict[str, Any]   # 사용자가 입력한 모든 값
    
class MascotPromptOption(BaseModel):
    style_name: str
    visual_prompt: str

class MascotPromptResponse(BaseModel):
    prompt_options: List[MascotPromptOption]
    
# 이미지 생성 스키마
class MascotImageGenerateRequest(BaseModel):
    member_no: str
    project_no: int
    promotion_type: str = "mascot"  # 고정
    prompt: MascotPromptOption       # 선택된 스타일 1개
    is_main: bool = True
