from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# --- 1단계 (/analyze) ---
class PosterTheme(BaseModel):
    """1단계 'theme' 입력"""
    theme: str = Field(..., description="사용자가 선택한 핵심 테마 (예: 감성/서정형)")

class AnalysisSummary(BaseModel):
    """1단계 Python 'analysis_summary' 객체 (Java DTO와 동일)"""
    title: str
    date: str
    location: str
    host: Optional[str] = None
    organizer: Optional[str] = None
    targetAudience: Optional[str] = None
    contactInfo: Optional[str] = None
    directions: Optional[str] = None
    programs: Optional[List[str]] = []
    events: Optional[List[str]] = []
    visualKeywords: Optional[List[str]] = []
    concept: Optional[str] = None

class PosterTrendReport(BaseModel):
    """1D단계 Python 'poster_trend_report' 객체"""
    status: str
    summary: Optional[str] = None
    top_creativity_example: Optional[Dict[str, Any]] = None

class StrategyReport(BaseModel):
    """1단계 Python 'strategy_report' 객체 (Java DTO와 동일)"""
    strategy_text: str
    proposed_content: Dict[str, Any]
    visual_reference_path: Optional[str] = None
    
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