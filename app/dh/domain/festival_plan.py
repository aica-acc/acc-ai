from pydantic import BaseModel, Field
from typing import List
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

    # --- OOP 로직 추가 ---
    def compare_theme(self, user_theme: str) -> dict:
        """유저 입력값과 기획서 요약 간 유사도 비교 후, 임계치에 따른 자동 판단"""
        emb_user = model.encode([user_theme])
        emb_plan = model.encode([self.summary])
        similarity = float(cosine_similarity(emb_user, emb_plan)[0][0])

        # 기본값
        decision = "require_confirmation"
        show_prompt = True

        # 유사도 구간별 판단
        if similarity >= 0.80:
            decision = "user"
            show_prompt = False
            message = (
                f"유사도 {similarity:.2f}: 기획서와 사용자 의도가 매우 유사합니다. "
                f"“{user_theme}”로 자동 진행합니다."
            )
        elif similarity >= 0.60:
            decision = "require_confirmation"
            show_prompt = True
            message = (
                f"유사도 {similarity:.2f}: 전반적으로 비슷합니다. "
                f"“{user_theme}”로 진행할까요?"
            )
        else:
            decision = "llm"
            show_prompt = True
            message = (
                f"유사도 {similarity:.2f}: 의미가 다릅니다. "
                f"기획서의 요약은 “{self.summary}”입니다. "
                f"당신의 의도(“{user_theme}”)로 진행할까요?"
            )

        return {
            "similarity": round(similarity, 3),
            "decision": decision,
            "show_prompt": show_prompt,
            "message": message,
            "options": {
                "yes": {"label": "예", "source": "user", "default_theme": user_theme},
                "no": {"label": "아니오", "source": "llm", "default_theme": self.summary},
            },
        }

    def summary_short(self) -> str:
        """한 줄 요약 (로깅용 / 리스트 출력용)"""
        return f"{self.title} @ {self.location} ({self.date})"
