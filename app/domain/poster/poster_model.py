from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# --- 1단계 (/analyze) ---

# --- 2단계 (/generate-prompt) ---
# 1단계의 전체 결과(JSON)를 받기 위한 모델
class GeneratePromptRequest(PosterTheme, AnalysisSummary, PosterTrendReport, StrategyReport):
    theme: str
    analysis_summary: Dict[str, Any]
    poster_trend_report: Dict[str, Any]
    strategy_report: Dict[str, Any]
    selected_formats: List[str] = Field(..., description="사용자가 선택한 규격 목록 (예: ['9:16', '1:1'])")

# --- 3단계 (/create-image) ---
# 2단계의 '선택된 시안'을 받기 위한 모델
class SelectedPromptData(BaseModel):
    style_name: str
    width: int
    height: int
    visual_prompt_for_background: str
    suggested_text_style: str

# 3단계 API가 '2가지' 정보를 받는 것을 정의
class CreateImageRequest(BaseModel):
    selected_prompt: SelectedPromptData
    analysis_summary: Dict[str, Any] # 텍스트 추출(v29)을 위해 1단계 요약본이 필요