from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from app.domain.cardnews.cardnews_score_model import CardNewsMetrics, CardNewsScore
from pydantic import ValidationError
import os

WEIGHTS = {
    "clarity": 0.18,
    "contrast": 0.15,
    "distraction": 0.12,
    "color_harmony": 0.18,
    "balance": 0.17,
    "semantic_fit": 0.20,
}

def analyze_image_features(image_path: str) -> CardNewsMetrics:
    """RAG/LLM 기반 카드뉴스 이미지 평가"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"이미지 없음: {image_path}")

    caption = f"이미지 '{os.path.basename(image_path)}'는 밝은 톤의 축제 현장을 표현하며 사람과 장식물이 어우러진 장면입니다."

    prompt = ChatPromptTemplate.from_template("""
    너는 시각 디자인 평가자야. 아래 이미지 설명을 보고 각 항목에 대해 0~10 사이의 점수를 JSON으로 반환해.

    항목:
    - clarity
    - contrast
    - distraction
    - color_harmony
    - balance
    - semantic_fit

    이미지 설명:
    {caption}
    """)

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    messages = prompt.format_messages(caption=caption)
    result = llm(messages)

    try:
        metrics = CardNewsMetrics.model_validate_json(result.content)
    except ValidationError as e:
        raise ValueError(f"LLM 응답 검증 실패: {e}")

    return metrics


def score_cardnews_image(image_path: str) -> CardNewsScore:
    """🎯 카드뉴스 이미지 점수화"""
    metrics = analyze_image_features(image_path)

    total_score = round(
        metrics.clarity * WEIGHTS["clarity"]
        + metrics.contrast * WEIGHTS["contrast"]
        + (10 - metrics.distraction) * WEIGHTS["distraction"]
        + metrics.color_harmony * WEIGHTS["color_harmony"]
        + metrics.balance * WEIGHTS["balance"]
        + metrics.semantic_fit * WEIGHTS["semantic_fit"],
        2,
    )

    return CardNewsScore(
        clarity_score=metrics.clarity,
        clarity_description="시각적으로 명료함" if metrics.clarity > 7 else "혼란스러움",
        contrast_score=metrics.contrast,
        contrast_description="피사체 대비 명확" if metrics.contrast > 7 else "대비 부족",
        distraction_score=metrics.distraction,
        distraction_description="불필요한 요소 거의 없음" if metrics.distraction < 7 else "시선 분산 요소 존재",
        color_harmony_score=metrics.color_harmony,
        color_harmony_description="톤 조화 우수" if metrics.color_harmony > 7 else "색상 불균형 존재",
        balance_score=metrics.balance,
        balance_description="시각적 균형 양호" if metrics.balance > 7 else "무게 중심 불균형",
        semantic_fit_score=metrics.semantic_fit,
        semantic_fit_description="주제와 일치" if metrics.semantic_fit > 7 else "맥락 일치도 낮음",
        total_score=total_score,
    )
