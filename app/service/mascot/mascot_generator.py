import os
import time
import json
from dotenv import load_dotenv

from app.service.mascot.mascot_prompt_graph import run_mascot_prompt_pipeline
from app.service.mascot.mascot_image_graph import run_mascot_image_pipeline

from app.core.config import PROMOTION_DIR

load_dotenv()

# 포스터와 같은 홍보물 폴더(PROMOTION_DIR) 아래에 저장한다.
# 백엔드는 python.base-dir(= PROMOTION_DIR) 기준으로 mascot/ 파일을 찾는다.
SAVE_DIR = str(PROMOTION_DIR / "mascot")
os.makedirs(SAVE_DIR, exist_ok=True)

def create_mascot_prompt(user_theme, analysis_summary, poster_trend_report, strategy_report):
    provided_context = f"""
    [User Theme]
    {user_theme}

    [Analysis Summary]
    {analysis_summary}

    [Poster Trend Report]
    {poster_trend_report}

    [Strategy Report]
    {strategy_report}
    """
    result = run_mascot_prompt_pipeline(provided_context)
    
    return result

def create_mascot_images(prompt_options):
    """
    Fail-Fast:
    - 하나라도 실패하거나
    - image_url/file_name/file_path/visual_prompt 중 하나라도 None이면
    → 즉시 종료 + status="error"
    """
    REQUIRED_KEYS = ["image_url", "file_name", "file_path", "visual_prompt"]

    print("===================================================")
    print("[mascot_generator] create_mascot_images 시작")
    print(f"[mascot_generator] prompt_options 개수 = {len(prompt_options)}")
    print("===================================================")

    results = []

    for i, opt in enumerate(prompt_options):
        style = opt.style_name
        raw_prompt = getattr(opt, "visual_prompt_for_background", None) or opt.visual_prompt

        print(f"👉 [{i+1}/{len(prompt_options)}] 스타일 생성: {style}")
        print(f"[mascot_generator]   raw_prompt 길이 = {len(raw_prompt)}")

        ts = int(time.time())
        filename = f"mascot_{ts}_{i}.png"
        filepath = os.path.join(SAVE_DIR, filename)
        
        print(f"[mascot_generator]   저장 예정 파일경로 = {filepath}")

        img = run_mascot_image_pipeline(
            style_name=style,
            raw_prompt=raw_prompt,
            output_path=filepath,
        )
        
        print("[mascot_generator]   run_mascot_image_pipeline 결과(raw) =")
        print(json.dumps(img, ensure_ascii=False, indent=2))

        # FAIL FAST: pipeline 실패
        if img.get("status") != "success":
            msg = img.get("message") or "IMAGE_PIPELINE_FAILED"
            print(f"[mascot_generator] ❌ pipeline 실패: {msg}")
            return {
                "status": "error",
                "error": msg,
                "failed_style": style,
            }

        print("===== VISUAL PROMPT DEBUG =====")
        print(f"raw_prompt: {raw_prompt!r}")
        print(f"opt.visual_prompt: {opt.visual_prompt!r}")
        print(f"최종 visual_prompt: {(raw_prompt or opt.visual_prompt)!r}")
        print("================================")

        rec = {
            "style_name": style,
            "image_url": img.get("image_url"),
            "file_name": filename,
            "file_path": filepath,
            "visual_prompt": raw_prompt or opt.visual_prompt,
            "text_content": None,
        }

        # FAIL FAST: 필수 필드 검증
        missing = [k for k in REQUIRED_KEYS if not rec.get(k)]
        if missing:
            msg = f"MISSING_CRITICAL_FIELDS {missing}"
            print(f"[mascot_generator] ❌ {msg}")
            return {
                "status": "error",
                "error": msg,
                "failed_style": style,
            }

        results.append(rec)

    if not results:
        return {
            "status": "error",
            "error": "NO_IMAGES_GENERATED",
        }

    return {
        "status": "success",
        "images": results,
    }
