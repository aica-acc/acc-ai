from app.tools.proposal.pdf_tools import analyze_pdf
from app.domain.festival.festival_plan import FestivalPlan

class FestivalService:
    """
    🎯 기획서 PDF 분석 및 사용자 테마 일치율 분석 서비스
    - analyze_pdf() → FestivalPlan 객체화 → compare_theme() → 결과 반환
    """

    def __init__(self):
        pass

    def analyze(self, pdf_path: str, user_theme: str, keywords: list, p_name: str):
        """
        1️⃣ PDF 분석
        2️⃣ FestivalPlan 변환
        3️⃣ 유저 테마와 비교
        4️⃣ 결과 반환
        """
        # 1️⃣ PDF 분석
        result = analyze_pdf(pdf_path)
        if "error" in result:
            return {"error": result["error"]}

        # 2️⃣ 기획서 도메인 객체 생성
        plan = FestivalPlan(**result)

        # 3️⃣ 유사도 비교
        comparison = plan.compare_theme(user_theme)

        # 4️⃣ 반환 구조 (기존과 동일)
        return {
            "p_name": p_name,
            "user_theme": user_theme,
            "keywords": keywords,
            "festival": plan.dict(),
            "analysis": {
                "similarity": comparison.get("similarity"),
                "decision": comparison.get("decision"),
                "original_theme": comparison.get("original_theme"),
                "corrected_theme": comparison.get("corrected_theme")
            }
        }
