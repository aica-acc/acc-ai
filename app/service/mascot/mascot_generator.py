import os
import json
from dotenv import load_dotenv

from app.service.mascot.mascot_prompt_graph import run_mascot_prompt_pipeline
from app.service.mascot.mascot_image_graph import run_mascot_image_pipeline

from pathlib import Path

from app.core.config import PROMOTION_DIR
from app.core.batch import batch_dir, result_name

load_dotenv()

# 포스터와 같은 홍보물 폴더(PROMOTION_DIR) 아래에 저장한다.
# 백엔드는 python.base-dir(= PROMOTION_DIR) 기준으로 mascot/ 파일을 찾는다.
SAVE_DIR = str(PROMOTION_DIR / "mascot")
os.makedirs(SAVE_DIR, exist_ok=True)

# 한 장이 실패했을 때 순서대로 재시도할 모델
FALLBACK_MODELS = ["recraft", "imagen"]


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

def create_mascot_images(prompt_options, batch=None):
    """
    결과는 {SAVE_DIR}/{batch}/mascot_{순번}_{프롬프트 해시}.png. 같은 파일이 있으면 다시 만들지 않는다 (#31).

    한 장이 실패해도 나머지는 끝까지 만들고, 실패 목록과 함께 status="error" 를 돌려준다.
    성공한 장은 폴더에 남겨 다시 요청하면 실패한 장만 만든다.
    (예전에는 첫 실패에서 멈추고 만든 파일을 모두 지웠다. 백엔드가 "폴더에 남은 4장"을 다른 프로젝트에 재사용할 수 있어서였다)
    """
    save_dir = batch_dir(Path(SAVE_DIR), batch)
    REQUIRED_KEYS = ["image_url", "file_name", "file_path", "visual_prompt"]

    print("===================================================")
    print("[mascot_generator] create_mascot_images 시작")
    print(f"[mascot_generator] prompt_options 개수 = {len(prompt_options)}")
    print("===================================================")

    results = []
    failed = []

    for i, opt in enumerate(prompt_options):
        style = opt.style_name
        raw_prompt = getattr(opt, "visual_prompt_for_background", None) or opt.visual_prompt

        print(f"👉 [{i+1}/{len(prompt_options)}] 스타일 생성: {style}")
        print(f"[mascot_generator]   raw_prompt 길이 = {len(raw_prompt)}")

        filename = result_name("mascot", i, raw_prompt)
        filepath = str(save_dir / filename)

        print(f"[mascot_generator]   저장 예정 파일경로 = {filepath}")

        if os.path.exists(filepath):
            print(f"[mascot_generator]   ♻️ 이미 만든 이미지 사용: {filename}")
            img = {"status": "success", "image_url": f"/poster-images/mascot/{filename}"}
        else:
            img = run_mascot_image_pipeline(
                style_name=style,
                raw_prompt=raw_prompt,
                output_path=filepath,
            )

        print("[mascot_generator]   run_mascot_image_pipeline 결과(raw) =")
        print(json.dumps(img, ensure_ascii=False, indent=2))

        # 실패하면 다른 모델로 재시도한다.
        # (예: flux 의 안전 필터가 평범한 마스코트를 NSFW 로 오탐해 거부하는 경우)
        if img.get("status") != "success":
            failed_model = img.get("model_name")
            for fallback in FALLBACK_MODELS:
                if fallback == failed_model:
                    continue
                print(f"[mascot_generator] ⚠️ {failed_model} 실패({img.get('error')}) → {fallback} 로 재시도")
                img = run_mascot_image_pipeline(
                    style_name=style,
                    raw_prompt=raw_prompt,
                    output_path=filepath,
                    model=fallback,
                )
                if img.get("status") == "success":
                    break

        # 재시도까지 실패: 이 장만 실패로 기록하고 나머지는 계속 만든다
        if img.get("status") != "success":
            msg = img.get("message") or img.get("error") or "IMAGE_PIPELINE_FAILED"
            print(f"[mascot_generator] ❌ pipeline 실패: {msg}")
            if os.path.exists(filepath):
                os.remove(filepath)  # 반쯤 쓰인 파일이 다음 요청에서 성공분으로 보이지 않게
            failed.append({"index": i, "style_name": style, "error": str(msg)})
            continue

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

    if failed or not results:
        return {
            "status": "error",
            "error": f"마스코트 {len(failed)}/{len(prompt_options)}장 생성 실패" if failed else "NO_IMAGES_GENERATED",
            "failed": failed,
            "succeeded": [r["file_name"] for r in results],
        }

    return {
        "status": "success",
        "images": results,
    }
