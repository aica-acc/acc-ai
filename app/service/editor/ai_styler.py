# app/service/editor/ai_styler.py

import base64
import json
from pathlib import Path
from typing import Dict, Any

from openai import OpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from dotenv import load_dotenv
load_dotenv()


client = OpenAI()
MODEL = "gpt-4o"


# ============================
# SYSTEM PROMPT (여기 보관)
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
- Use color palettes directly sampled from the background image.
- Apply strong multi-layer strokes (e.g., gold outer stroke + darker inner outline).
- Apply professional glow/ambient light around text.
- Add subtle gradient-like effects using fill + stroke combinations.
- Use deep shadows for depth and 3D presence.
- Typography must feel premium, festival, celebratory.

Tone:
Do NOT be conservative. Apply meaningful, visible improvements.
Final style should look like real printed outdoor festival signage.

Return JSON:
{"updatedCanvas": <canvasJson>}
"""


# =================================================================
# util: 이미지 파일 URL → base64 dataURL
# =================================================================
def load_image_as_data_url(image_path: str) -> str:
    """
    /static/editor/xxx.png 처럼 로컬 파일을 base64로 변환하고
    data:image/png;base64,... 형태로 반환
    """

    path_obj = Path(image_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없음: {image_path}")

    mime = "image/png"
    if image_path.lower().endswith(".jpg") or image_path.lower().endswith(".jpeg"):
        mime = "image/jpeg"

    with open(path_obj, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime};base64,{encoded}"


# =================================================================
# LangChain 스타일러 파이프라인
# =================================================================
def run_style_pipeline(background_image_url_or_path: str,
                       canvas_json: Dict[str, Any],
                       layout_type: str):
    """
    1) 이미지가 URL or file path인지 감지
    2) 필요하면 base64 변환
    3) LLM으로 스타일 렌더링 요청
    """

    # base64 변환 자동 감지
    if background_image_url_or_path.startswith("http"):
        # URL인 경우 → 클라이언트가 dataURL로 줬다고 가정
        background_data_url = background_image_url_or_path
    else:
        # 로컬 파일인 경우
        background_data_url = load_image_as_data_url(background_image_url_or_path)

    payload_text = json.dumps({
        "layoutType": layout_type,
        "canvasJson": canvas_json
    }, ensure_ascii=False)

    # ============================
    # LangChain prompt
    # ============================
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("user", [
            {
                "type": "text",
                "text": f"LayoutType: {layout_type}"
            },
            {
                "type": "image_url",
                "image_url": {"url": background_data_url}
            },
            {
                "type": "text",
                "text": payload_text
            }
        ])
    ])

    chain = prompt | client.chat.completions.create | JsonOutputParser()

    llm_response = chain.invoke({
        "layoutType": layout_type,
        "canvasJson": canvas_json
    })

    return llm_response["updatedCanvas"]
