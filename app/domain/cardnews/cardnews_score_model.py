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
