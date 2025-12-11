import os
import json
import base64
from pathlib import Path
from openai import OpenAI
from typing import Dict, Any
from dotenv import load_dotenv
load_dotenv()
# ============================
# 1. 설정
# ============================
client = OpenAI()
MODEL = "gpt-4o"
BASE_DIR = Path(__file__).resolve().parent
TEST_JSON_PATH = BASE_DIR / "test_input.json"
OUTPUT_JSON_PATH = BASE_DIR / "test_output.json"


# ============================
# 2. LLM 프롬프트
# ============================

SYSTEM_PROMPT = """
You are a Fabric.js advanced poster typography designer.

Goal:
Transform the given text elements into high–quality, festival-grade poster typography.
Use bold, vivid, polished styling similar to professional event banners.

NEVER modify:
- text content
- coordinates (left, top), width/height
- angle, scale, origin, flip, skew

You MAY modify only style fields:
fontFamily, fontSize, fontWeight, fontStyle,
fill, stroke, strokeWidth,
shadow (inner/outer), opacity,
charSpacing, lineHeight,
textBackgroundColor, textAlign, underline, linethrough.

Styling rules:
- Use color palettes directly sampled from the background image (warm yellows, golds, reds, oranges).
- Apply strong multi-layer strokes (e.g., gold outer stroke + darker inner outline).
- Apply professional glow/ambient light around text for readability.
- Add subtle gradient-like effects using fill + stroke combinations.
- Use deep shadows for depth and 3D presence.
- Typography must feel “premium”, “festival”, “celebratory”.

Tone:
Do NOT be conservative. Apply meaningful, visible improvements.
Final style should look like real printed outdoor festival signage.

Return JSON:
{"updatedCanvas": <canvasJson>}

"""


# ============================
# 3. 이미지 + JSON 스타일러
# ============================

def llm_style_canvas_with_image(background_image_data_url: str,
                                canvas_json: Dict[str, Any],
                                layout_type: str):

    payload_text = json.dumps({
        "layoutType": layout_type,
        "canvasJson": canvas_json,
    }, ensure_ascii=False)

    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"LayoutType: {layout_type}. Style the text based on the background image."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": background_image_data_url
                        }
                    },
                    {
                        "type": "text",
                        "text": payload_text
                    }
                ]
            }
        ],
    )

    result_json = json.loads(response.choices[0].message.content)
    return result_json["updatedCanvas"]


# ============================
# 4. 테스트 실행
# ============================

def main():
    if not TEST_JSON_PATH.exists():
        raise FileNotFoundError("test_input.json 파일이 필요합니다.")

    data = json.loads(TEST_JSON_PATH.read_text(encoding="utf-8"))
    layout_type = data["layoutType"]
    background_image_data_url = data["backgroundImage"]
    canvas_json = data["canvasJson"]

    updated = llm_style_canvas_with_image(
        background_image_data_url,
        canvas_json,
        layout_type,
    )

    OUTPUT_JSON_PATH.write_text(
        json.dumps(updated, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("완료! 결과 JSON →", OUTPUT_JSON_PATH)


main()
