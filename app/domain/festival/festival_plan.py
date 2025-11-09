from pydantic import BaseModel, Field
from typing import List, Optional
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

class FestivalPlan(BaseModel):
    title: str = ""
    date: str = ""
    location: str = ""
    host: str = ""
    organizer: str = ""
    targetAudience: str = ""
    summary: str = ""
    programs: List[str] = Field(default_factory=list)
    events: List[str] = Field(default_factory=list)
    visualKeywords: List[str] = Field(default_factory=list)
    contactInfo: str = ""
    directions: str = ""

    # 테마 비교용 필드
    original_theme: Optional[str] = None
    corrected_theme: Optional[str] = None

    def compare_theme(self, user_theme: str) -> dict:
        """
        유저 입력값과 기획서 요약 간 유사도 비교.
        유사도 임계치에 따라 user / require_confirmation / llm 판별.
        """
        if not self.summary:
            return {"error": "summary 필드가 비어 있습니다."}

        emb_user = model.encode([user_theme])
        emb_plan = model.encode([self.summary])
        similarity = float(cosine_similarity(emb_user, emb_plan)[0][0])

        decision = "require_confirmation"
        corrected_theme = user_theme

        if similarity >= 0.80:
            decision = "user"
        elif similarity < 0.60:
            decision = "llm"
            corrected_theme = self.summary

        self.original_theme = user_theme
        self.corrected_theme = corrected_theme

        return {
            "similarity": round(similarity, 3),
            "decision": decision,
            "original_theme": user_theme,
            "corrected_theme": corrected_theme
        }

    def summary_short(self) -> str:
        return f"{self.title or '제목없음'} @ {self.location or '위치미상'} ({self.date or '날짜미상'})"
