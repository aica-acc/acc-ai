from fastapi import APIRouter
from app.service.cardnews.cardnews_prompt_service import build_prompt_for_review

router = APIRouter()

@router.post("/generate-prompt")
def generate_prompt(payload: dict):
    references = payload["references"]
    user_theme = payload.get("user_theme")
    keywords = payload.get("keywords")

    prompt_data = build_prompt_for_review(references, user_theme, keywords)

    return {
        "visual_prompt": prompt_data["visual_prompt"],
        "style_name": prompt_data["style_name"]
    }
