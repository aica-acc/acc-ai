# app/service/editor/ai_styler.py

import base64
import json
import os
import requests
from pathlib import Path
from typing import Dict, Any

from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

# PROJECT_ROOT 환경변수 가져오기
PROJECT_ROOT = os.getenv("PROJECT_ROOT")
if PROJECT_ROOT:
    PROJECT_ROOT = Path(PROJECT_ROOT).resolve()
else:
    PROJECT_ROOT = None

# Static URL prefix
STATIC_BASE_URL = os.getenv("STATIC_BASE_URL", "http://127.0.0.1:5000/static/editor")


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
opacity,
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
# util: 이미지 파일/URL → base64 dataURL
# =================================================================
def load_image_as_data_url(image_path_or_url: str) -> str:
    """
    로컬 파일 경로 또는 URL을 base64로 변환하고
    data:image/png;base64,... 형태로 반환
    
    - 로컬 파일: /static/editor/xxx.png 또는 C:/path/to/file.png
    - URL: http://127.0.0.1:5000/static/... (다운로드 후 변환)
    - data URL: data:image/... (그대로 반환)
    """
    
    # 이미 data URL인 경우 그대로 반환
    if image_path_or_url.startswith("data:image/"):
        return image_path_or_url
    
    # URL인 경우 처리
    if image_path_or_url.startswith("http://") or image_path_or_url.startswith("https://"):
        # 로컬 서버 URL인 경우 파일 경로로 변환 시도
        if STATIC_BASE_URL and image_path_or_url.startswith(STATIC_BASE_URL):
            # http://127.0.0.1:5000/static/editor/28/clean/bus_road.png
            # → PROJECT_ROOT/app/data/editor/28/clean/bus_road.png
            if PROJECT_ROOT:
                # /static/editor/ 이후 경로 추출
                static_path = image_path_or_url.replace(STATIC_BASE_URL, "").lstrip("/")
                local_path = PROJECT_ROOT / "app" / "data" / "editor" / static_path
                
                if local_path.exists():
                    # 로컬 파일로 읽기
                    mime = "image/png"
                    if str(local_path).lower().endswith((".jpg", ".jpeg")):
                        mime = "image/jpeg"
                    
                    with open(local_path, "rb") as f:
                        encoded = base64.b64encode(f.read()).decode("utf-8")
                    return f"data:{mime};base64,{encoded}"
        
        # 로컬 파일로 변환 실패하거나 외부 URL인 경우 다운로드
        try:
            response = requests.get(image_path_or_url, timeout=60)  # 타임아웃 60초로 증가
            response.raise_for_status()
            image_data = response.content
            
            # MIME 타입 결정
            content_type = response.headers.get("Content-Type", "image/png")
            if "jpeg" in content_type or "jpg" in content_type:
                mime = "image/jpeg"
            elif "png" in content_type:
                mime = "image/png"
            else:
                # 파일 확장자로 판단
                if image_path_or_url.lower().endswith((".jpg", ".jpeg")):
                    mime = "image/jpeg"
                else:
                    mime = "image/png"
            
            encoded = base64.b64encode(image_data).decode("utf-8")
            return f"data:{mime};base64,{encoded}"
        except Exception as e:
            raise FileNotFoundError(f"이미지 URL 다운로드 실패: {image_path_or_url}, 에러: {e}")
    
    # 로컬 파일 경로인 경우
    path_obj = Path(image_path_or_url)
    if not path_obj.exists():
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없음: {image_path_or_url}")

    mime = "image/png"
    if image_path_or_url.lower().endswith((".jpg", ".jpeg")):
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

    # 모든 경우에 대해 base64로 변환 (URL, 로컬 파일, data URL 모두 처리)
    background_data_url = load_image_as_data_url(background_image_url_or_path)

    # 페이로드 텍스트 생성
    payload_text = json.dumps({
        "layoutType": layout_type,
        "canvasJson": canvas_json
    }, ensure_ascii=False)

    # ============================
    # 직접 OpenAI API 호출
    # ============================
    layout_text = f"LayoutType: {layout_type}"
    
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.7,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": layout_text
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": background_data_url
                        }
                    },
                    {
                        "type": "text",
                        "text": payload_text
                    }
                ]
            }
        ],
        response_format={"type": "json_object"}  # JSON 응답 강제
    )

    # 응답에서 JSON 파싱
    if not response.choices or len(response.choices) == 0:
        raise ValueError("OpenAI API 응답에 choices가 없습니다.")
    
    response_text = response.choices[0].message.content
    if not response_text:
        raise ValueError("OpenAI API 응답 내용이 비어있습니다.")
    
    try:
        llm_response = json.loads(response_text)
        
        # updatedCanvas 필드 확인
        if "updatedCanvas" not in llm_response:
            raise ValueError(f"AI 응답에 updatedCanvas 필드가 없습니다. 응답: {response_text}")
        
        return llm_response["updatedCanvas"]
    except json.JSONDecodeError as e:
        raise ValueError(f"AI 서버 응답 JSON 파싱 실패: {response_text}, 에러: {e}")
