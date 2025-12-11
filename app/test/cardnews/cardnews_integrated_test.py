from __future__ import annotations
from dotenv import load_dotenv
import json
from pathlib import Path
from datetime import datetime
import requests
from io import BytesIO
from PIL import Image

from app.service.cardnews.cardnews_prompt_service import build_prompt_for_review
from app.service.cardnews.replicate_image_generator import generate_image_from_prompt
from app.service.cardnews.text_overlay_service import compose_cardnews
from app.domain.cardnews.cardnews_prompt_model import TableData, TableCell, TableRow

# ====== 1. 기본 경로 설정 ======
BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")

OUTPUT_DIR = BASE_DIR / "data" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FONTS_BASE = BASE_DIR / "data" / "nanum-all_new" / "나눔 글꼴"

# ====== 2. 테스트용 레퍼런스 데이터 ======
TEST_REFERENCES = [
    {
        "festival_name": "2025 김제 모악뮤직페스티벌",
        "category": "부스소개",
        "title": "너랑 본 벚꽃이 마지막이었으면",
        "file_path": "dummy.jpg",
        "source_url": "",
        "year": 2025,
        "region": "전북",
        "score": {
            "total_score": 8.2,
            "clarity_score": 8,
            "clarity_description": "텍스트 구성이 안정적",
            "contrast_score": 7,
            "contrast_description": "배경 대비 양호",
            "distraction_score": 6,
            "distraction_description": "약간 산만함",
            "color_harmony_score": 8,
            "color_harmony_description": "따뜻한 색조 조화",
            "balance_score": 7,
            "balance_description": "중앙 배치 양호",
            "semantic_fit_score": 9,
            "semantic_fit_description": "축제 컨셉과 잘 맞음"
        }
    }
]


# ====== 3. 표 데이터 ======
TEST_TABLE = TableData(
    headers=["항목", "내용"],
    rows=[
        TableRow(cells=[TableCell(value="일정"), TableCell(value="2025.04.26 ~ 04.27")]),
        TableRow(cells=[TableCell(value="장소"), TableCell(value="김제 모악산 금산사")]),
        TableRow(cells=[TableCell(value="문의"), TableCell(value="063-000-0000")]),
    ]
)

# ====== 4. 본문 텍스트 ======
TEST_TEXT = {
    "title": "2025 김제 모악뮤직페스티벌",
    "subtitle": "벚꽃과 음악이 함께하는 감성 봄 축제",
}


# ====== 이미지 URL 다운로드 ======
def download_image_to_local(url: str, save_path: Path) -> Path:
    resp = requests.get(url)
    img = Image.open(BytesIO(resp.content)).convert("RGB")
    img.save(save_path)
    return save_path


# ====== 실제 테스트 수행 ======
def run_test():

    print("🔥 Step1: 프롬프트 생성 중...")
    prompt_data = build_prompt_for_review(
        references=TEST_REFERENCES,
        user_theme="봄 감성 + 가족 중심",
        keywords=["벚꽃", "가족", "음악"]
    )
    vp = prompt_data["visual_prompt"]
    style = prompt_data["style_name"]
    print("✓ 프롬프트 생성 완료")

    print("🔥 Step2: 배경 이미지 생성 중...")
    bg_url = generate_image_from_prompt(vp)
    print("✓ Replicate 이미지 생성 완료:", bg_url)

    # ===== URL → 로컬로 다운로드 =====
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    local_bg_path = OUTPUT_DIR / f"background_{timestamp}.png"
    download_image_to_local(bg_url, local_bg_path)

    final_png = OUTPUT_DIR / f"cardnews_test_{timestamp}.png"
    result_json = OUTPUT_DIR / f"cardnews_test_{timestamp}.json"

    print("🔥 Step3: 카드뉴스 오버레이 생성 중...")

    # ===== compose_cardnews에 필요한 layout_config 구성 =====
    layout_config = {
        "title": {
            "text": TEST_TEXT["title"],
            "position": [80, 80],
            "font_size": 72,
            "use_box": True,
        },
        "subtitle": {
            "text": TEST_TEXT["subtitle"],
            "position": [80, 180],
            "font_size": 44,
        },
        "table": {
            "table": TEST_TABLE,
            "position": [80, 330],
            "col_widths": [300, 650],
        },
    }

    compose_cardnews(
        background_path=str(local_bg_path),
        output_path=str(final_png),
        layout_config=layout_config,
        fonts_dir=str(FONTS_BASE)
    )
    print("✓ 최종 이미지 생성 완료:", final_png)

    print("🔥 Step4: JSON 기록 중...")
    result_json.write_text(
        json.dumps(
            {
                "visual_prompt": vp,
                "style_name": style,
                "background_url": bg_url,
                "background_local_path": str(local_bg_path),
                "output_image": str(final_png)
            },
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )
    print("✓ JSON 저장 완료:", result_json)

    print("\n🎉 ALL DONE — 테스트 성공!\n")


if __name__ == "__main__":
    run_test()
