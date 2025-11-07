from app.dh.tools.pdf_tools import analyze_pdf
from app.dh.domain.festival_plan import FestivalPlan

class FestivalService:
    def __init__(self):
        pass

    def analyze(self, pdf_path: str, user_theme: str, keywords: list, p_name: str):
        result = analyze_pdf(pdf_path)
        if "error" in result:
            return {"error": result["error"]}

        plan = FestivalPlan(**result)
        comparison = plan.compare_theme(user_theme)

        return {
            "p_name": p_name,
            "user_theme": user_theme,
            "keywords": keywords,
            "festival": plan.dict(),
            "analysis": comparison
        }
