import os
import cv2
import torch
import clip
import numpy as np
from datetime import datetime
from PIL import Image

from transformers import BlipProcessor, BlipForConditionalGeneration
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import ValidationError

from app.domain.cardnews.cardnews_score_model import CardNewsMetrics, CardNewsScore

# GPU 강제 비활성화 (서버 환경 안정성 위해)
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

def cv2_imread_unicode(path: str):
    """
    Windows + 한글 경로 대응용 imread 래퍼
    """
    path = str(path)
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    return img

# ===============================================================
# 1️⃣ BLIP Captioning: 이미지 → 텍스트 요약
# ===============================================================
processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

device = "cuda" if torch.cuda.is_available() else "cpu"
clip_model, clip_preprocess = clip.load("ViT-B/32", device=device)

# LLM & Pydantic 파서 (전역 1회만 생성)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
parser = PydanticOutputParser(pydantic_object=CardNewsMetrics)

# LLM용 프롬프트 (네가 제안한 고도화 버전 반영)
cardnews_metrics_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "너는 축제 홍보용 카드뉴스를 평가하는 시각디자인 전문가다. "
                "배너, 포스터, 인스타그램 카드뉴스 등 디지털 홍보물을 많이 접해본 전문가 기준으로 평가한다. "
                "반드시 지시한 JSON 형식만 반환해야 하며, 설명은 모두 자연스러운 한국어로 작성한다."
            ),
        ),
        (
            "user",
            """
아래는 **카드뉴스 이미지 한 장**을 사람이 설명한 텍스트다.
이 설명을 바탕으로 카드뉴스의 시각적 완성도를 평가해라.

### 1. 점수 범위와 해석

각 점수는 0.0 ~ 10.0 사이의 실수(float)로 평가한다.

- 0.0 ~ 3.0  : 매우 부족 — 심각하게 문제 있는 수준, 실제 서비스에 쓰기 어려움
- 3.1 ~ 5.0  : 부족 — 개선해야 할 점이 많음
- 5.1 ~ 7.0  : 보통 — 실사용은 가능하지만 다듬을 부분이 있음
- 7.1 ~ 8.5  : 우수 — 전체적으로 완성도가 높고 실무에서도 충분히 사용 가능
- 8.6 ~ 10.0 : 매우 우수 — 다른 사례의 레퍼런스로 사용할 만한 높은 완성도

### 2. 평가 항목 정의

1) clarity_score / clarity_description  (시각적 명료도)
- 핵심 정보(축제명, 날짜, 장소, 주요 메시지)가 한눈에 들어오는지
- 글자 크기, 계층 구조(타이틀/서브타이틀/본문)가 명확한지
- 불필요하게 복잡한 요소 때문에 정보 파악이 방해되지 않는지

2) contrast_score / contrast_description  (명도 대비·가독성)
- 배경색과 텍스트 색의 대비가 충분한지
- 중요한 정보일수록 대비가 강하게 처리되어 있는지
- 흰색/검정/포인트 컬러 사용이 가독성을 높이는 방향으로 쓰였는지

3) distraction_score / distraction_description  (방해요소·시선 분산 정도)
- 불필요한 아이콘, 장식, 패턴, 과도한 이펙트가 시선을 빼앗지 않는지
- 정보 전달과 상관없는 요소가 너무 많지 않은지
- 하나의 주요 시선 흐름(focal point)이 유지되는지

4) color_harmony_score / color_harmony_description  (색상 조화·통일감)
- 메인 컬러/포인트 컬러가 일관되게 사용되는지
- 브랜드/축제 컨셉과 어울리는 색 조합인지
- 색이 너무 많거나 튀어서 전체적으로 산만하지는 않은지

5) balance_score / balance_description  (레이아웃 균형·구성)
- 좌우/상하 무게 중심이 적절하게 분배되어 있는지
- 텍스트 박스, 이미지, 아이콘의 배치가 안정적으로 느껴지는지
- 여백(화이트 스페이스)이 충분히 확보되어 답답하지 않은지

6) semantic_fit_score / semantic_fit_description  (주제 적합도, 선택적)
- 축제의 주제(예: 벚꽃, 우주, 음식, 가족, 지역 특산물 등)와 시각 요소가 얼마나 잘 맞는지
- 이미지/색상/아이콘/일러스트가 축제의 성격과 타겟(가족, MZ, 지역 주민 등)에 적합한지
- 단순히 예쁘기만 한 것이 아니라, “이 카드뉴스를 보면 어떤 축제인지”가 자연스럽게 느껴지는지
- **자동 배치에서 기획의도 정보가 전혀 없는 경우**, 대략적인 느낌만으로 평가하되,
  판단이 어려우면 5.0 근처의 중립적인 점수를 줄 수 있다.

### 3. total_score 계산 규칙

- total_score는 다음 항목을 동일 가중치로 평균 낸 값으로 한다.

  - clarity_score
  - contrast_score
  - (10 - distraction_score)  → 방해요소가 적을수록 좋은 카드뉴스이므로,
  - color_harmony_score
  - balance_score
  - semantic_fit_score 가 존재한다면 포함, 없다면 나머지 항목만으로 평균

- 소수점 둘째 자리에서 반올림하여 소수점 첫째 자리까지 남긴다. (예: 7.36 → 7.4)

### 4. 설명(description) 작성 규칙

- 각 *_description은 한글 1~3문장 정도로 구체적으로 작성한다.
- 단순히 “좋다/나쁘다”가 아니라, **레이아웃·색·텍스트 배치·요소 선택** 등
  시각적인 특성이 드러나도록 서술한다.
- 예)
  - clarity_description 예시:
    - "축제명과 날짜가 화면 상단에 크게 배치되어 첫눈에 들어오며, 서브 정보는 그 아래에 단계적으로 정리되어 있다."
  - color_harmony_description 예시:
    - "메인 컬러인 파란색과 보조 컬러인 노란색이 반복 사용되어 통일감이 있고, 과도하게 튀는 색은 없다."

### 5. 출력 형식 (JSON ONLY)

- 반드시 **순수 JSON**만 반환한다.
- 설명 텍스트나 해설, 마크다운, 코드 블록(````json`)을 추가로 쓰지 않는다.
- 아래 `JSON 스키마 설명`을 엄격히 따르라.

{format_instructions}

---

아래는 사람이 묘사한 카드뉴스 이미지 설명이다. 이 설명만 보고 위 기준에 따라 평가하라.

[이미지 설명 시작]
{caption}
[이미지 설명 끝]
""",
        ),
    ]
).partial(format_instructions=parser.get_format_instructions())


def generate_caption(image_path: str) -> str:
    """BLIP 기반 이미지 캡션 생성"""
    raw_image = Image.open(image_path).convert("RGB")
    inputs = processor(raw_image, return_tensors="pt").to(device)
    out = model.generate(**inputs, max_new_tokens=60)
    caption = processor.decode(out[0], skip_special_tokens=True)
    return caption


# ===============================================================
# 2️⃣ LLM 기반 평가 (고도화된 프롬프트 + Pydantic 파서)
# ===============================================================
def analyze_image_features_llm(image_path: str, caption: str) -> CardNewsMetrics:
    """
    BLIP Caption + LLM 기반 시각 품질 점수화

    - 프롬프트는 카드뉴스 전문 디자이너 관점의 기준을 상세히 포함
    - PydanticOutputParser를 사용해 CardNewsMetrics 스키마에 맞춰 구조화
    """
    try:
        metrics: CardNewsMetrics = (cardnews_metrics_prompt | llm | parser).invoke(
            {"caption": caption}
        )

        # 안전을 위해 total_score를 한 번 더 코드에서 재계산해도 됨
        scores_for_total = [
            metrics.clarity_score,
            metrics.contrast_score,
            10 - metrics.distraction_score,  # 방해 요소는 낮을수록 좋음
            metrics.color_harmony_score,
            metrics.balance_score,
        ]

        # semantic_fit_score가 있을 때만 포함
        if metrics.semantic_fit_score is not None:
            scores_for_total.append(metrics.semantic_fit_score)

        metrics.total_score = round(float(np.mean(scores_for_total)), 1)
        metrics.create_at = datetime.now()
        return metrics

    except ValidationError as e:
        raise ValueError(f"LLM 응답 검증 실패: {e}")


# ===============================================================
# 3️⃣ CLIP + OpenCV 기반 평가 (객관적 수치형)
# ===============================================================
def score_cardnews_image(image_path: str, text_prompt: str | None = None) -> CardNewsScore:
    """CLIP + OpenCV 기반 객관적 시각 점수화"""

    img = cv2_imread_unicode(image_path)
    if img is None:
        raise ValueError(f"이미지를 불러올 수 없습니다: {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # === Clarity (글자/요소 선명도) ===
    clarity_val = cv2.Laplacian(gray, cv2.CV_64F).var()
    clarity_score = np.clip(clarity_val / 500, 0, 10)
    clarity_description = (
        "텍스트 및 주요 요소가 선명하게 구분됨" if clarity_score > 6 else "텍스트와 배경의 구분이 다소 흐림"
    )

    # === Contrast (명도 대비) ===
    contrast_val = np.std(gray)
    contrast_score = np.clip(contrast_val / 25, 0, 10)
    contrast_description = (
        "명암 대비가 뚜렷하여 정보 전달이 용이함" if contrast_score > 6 else "대비가 낮아 시각적으로 평면적인 인상"
    )

    # === Distraction (산만함) ===
    p = cv2.calcHist([gray], [0], None, [256], [0, 256]) / gray.size
    entropy = -np.sum(p * np.log2(p + 1e-7))
    distraction_score = np.clip(10 - (entropy / 0.8), 0, 10)
    distraction_description = (
        "불필요한 장식 요소가 적고 시선 집중이 용이함" if distraction_score > 6 else "시각적 요소가 산만함"
    )

    # === Color Harmony (색상 조화) ===
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hist_hue = cv2.calcHist([hsv], [0], None, [50], [0, 180])
    hist_hue = hist_hue / hist_hue.sum()
    color_harmony_score = np.clip(10 - np.std(hist_hue) * 100, 0, 10)
    color_harmony_description = (
        "색상 팔레트의 통일성이 높음" if color_harmony_score > 6 else "색상 조합이 다소 불균형함"
    )

    # === Balance (레이아웃 균형) ===
    h, w = gray.shape
    
    left_weight  = float(np.sum(gray[:, : w // 2]))
    right_weight = float(np.sum(gray[:, w // 2:]))

    denom = left_weight + right_weight + 1e-7
    ratio = abs(left_weight - right_weight) / denom  # 0~1

    balance_score = float(np.clip(10 - ratio * 10, 0, 10))
    balance_description = (
        "좌우 시각적 균형이 안정적" if balance_score > 6 else "한쪽으로 무게 중심이 치우침"
    )

    # === Semantic Fit (주제 적합도) ===
    if text_prompt:
        image_pil = Image.open(image_path).convert("RGB")
        image_input = clip_preprocess(image_pil).unsqueeze(0).to(device)
        text_input = clip.tokenize([text_prompt]).to(device)
        with torch.no_grad():
            image_features = clip_model.encode_image(image_input)
            text_features = clip_model.encode_text(text_input)
            similarity = torch.cosine_similarity(image_features, text_features).item()
        semantic_fit_score = np.clip(similarity * 10, 0, 10)
        semantic_fit_description = (
            "이미지가 기획 의도와 잘 일치함" if semantic_fit_score > 6 else "시각 요소와 기획 의도가 다소 어긋남"
        )
    else:
        # 자동 배치(기획의도 없음)에서는 중립값 5.0 + 설명
        semantic_fit_score = 5.0
        semantic_fit_description = "기획의도 정보가 없어 주제 적합도를 중립적으로 평가함"

    # total_score는 hybrid에서 다시 계산
    return CardNewsScore(
        clarity_score=round(clarity_score, 2),
        clarity_description=clarity_description,
        contrast_score=round(contrast_score, 2),
        contrast_description=contrast_description,
        distraction_score=round(distraction_score, 2),
        distraction_description=distraction_description,
        color_harmony_score=round(color_harmony_score, 2),
        color_harmony_description=color_harmony_description,
        balance_score=round(balance_score, 2),
        balance_description=balance_description,
        semantic_fit_score=round(semantic_fit_score, 2),
        semantic_fit_description=semantic_fit_description,
        total_score=0.0,
        create_at=datetime.now(),
    )


# ===============================================================
# 4️⃣ Hybrid 평가 결합 (LLM + CLIP)
# ===============================================================
def hybrid_cardnews_score(image_path: str, text_prompt: str | None = None) -> CardNewsMetrics:
    """
    🎯 CLIP + LLM 하이브리드 카드뉴스 품질 점수화

    - text_prompt None → 자동배치 (semantic_fit을 total_score 계산에서 제외)
    - text_prompt 존재 → 생성물 평가 (semantic_fit 포함)
    """

    # === Step 1: Caption 생성 ===
    caption = generate_caption(image_path)

    # === Step 2: 두 평가 실행 ===
    llm_metrics = analyze_image_features_llm(image_path, caption)  # CardNewsMetrics
    clip_metrics = score_cardnews_image(image_path, text_prompt=text_prompt)  # CardNewsScore

    # === Step 3: 수치 하이브리드 (단순 평균) ===
    def avg(a: float, b: float) -> float:
        return round((a + b) / 2, 2)

    clarity_score = avg(llm_metrics.clarity_score, clip_metrics.clarity_score)
    contrast_score = avg(llm_metrics.contrast_score, clip_metrics.contrast_score)
    distraction_score = avg(llm_metrics.distraction_score, clip_metrics.distraction_score)
    color_harmony_score = avg(llm_metrics.color_harmony_score, clip_metrics.color_harmony_score)
    balance_score = avg(llm_metrics.balance_score, clip_metrics.balance_score)

    if text_prompt:
        semantic_fit_score = avg(llm_metrics.semantic_fit_score, clip_metrics.semantic_fit_score)
        semantic_fit_description = llm_metrics.semantic_fit_description
    else:
        # 자동 배치에서는 semantic_fit은 기록만 남기고 total_score 계산에서는 제외
        semantic_fit_score = 0.0
        semantic_fit_description = clip_metrics.semantic_fit_description

    # === Step 4: total_score 재계산 ===
    scores_for_total = [
        clarity_score,
        contrast_score,
        10 - distraction_score,  # 방해요소는 낮을수록 좋으므로 뒤집어서 사용
        color_harmony_score,
        balance_score,
    ]
    if text_prompt:
        scores_for_total.append(semantic_fit_score)

    total_score = round(float(np.mean(scores_for_total)), 1)

    # === Step 5: 최종 CardNewsMetrics로 반환 (DB cardnews_score 매핑 기준)
    return CardNewsMetrics(
        clarity_score=clarity_score,
        clarity_description=llm_metrics.clarity_description,
        contrast_score=contrast_score,
        contrast_description=llm_metrics.contrast_description,
        distraction_score=distraction_score,
        distraction_description=llm_metrics.distraction_description,
        color_harmony_score=color_harmony_score,
        color_harmony_description=llm_metrics.color_harmony_description,
        balance_score=balance_score,
        balance_description=llm_metrics.balance_description,
        semantic_fit_score=semantic_fit_score,
        semantic_fit_description=semantic_fit_description,
        total_score=total_score,
        create_at=datetime.now(),
    )
