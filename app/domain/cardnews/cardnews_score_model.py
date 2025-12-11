from pydantic import BaseModel, Field
from datetime import datetime

class CardNewsScore(BaseModel):
    clarity_score: float
    clarity_description: str
    contrast_score: float
    contrast_description: str
    distraction_score: float
    distraction_description: str
    color_harmony_score: float
    color_harmony_description: str
    balance_score: float
    balance_description: str
    semantic_fit_score: float
    semantic_fit_description: str
    total_score: float
    create_at: datetime = Field(default_factory=datetime.now)

class CardNewsMetrics(BaseModel):
    """카드뉴스 이미지 품질 지표 모델 (LLM/CLIP 점수화 공통 스키마)"""

    clarity_score: float = Field(..., description="시각적 명료도 점수")
    clarity_description: str = Field(..., description="시각적 명료도 설명")

    contrast_score: float = Field(..., description="명도 대비 점수")
    contrast_description: str = Field(..., description="명도 대비 설명")

    distraction_score: float = Field(..., description="방해요소 점수")
    distraction_description: str = Field(..., description="방해요소 설명")

    color_harmony_score: float = Field(..., description="색상 조화도 점수")
    color_harmony_description: str = Field(..., description="색상 조화도 설명")

    balance_score: float = Field(..., description="시각적 균형 점수")
    balance_description: str = Field(..., description="시각적 균형 설명")

    semantic_fit_score: float = Field(..., description="주제 적합도 점수")
    semantic_fit_description: str = Field(..., description="주제 적합도 설명")

    total_score: float = Field(..., description="종합 점수 (가중 평균)")
    create_at: datetime = Field(default_factory=datetime.now, description="평가 시점")

    class Config:
        extra = "ignore"  # LLM 응답에 예상치 못한 필드가 있어도 무시

