# app/routes/editor.py

from fastapi import APIRouter
from app.service.editor.ai_styler import run_style_pipeline

router = APIRouter(prefix="/editor", tags=["Editor AI"])

@router.post("/render")
async def render_with_ai(payload: dict):
    print("🚀 [EditorAI] /editor/render 호출됨")
    
    try:
        # 필수 필드 확인
        if "backgroundImage" not in payload:
            raise ValueError("backgroundImage 필드가 없습니다.")
        if "canvasJson" not in payload:
            raise ValueError("canvasJson 필드가 없습니다.")
        
        updated = run_style_pipeline(
            background_image_url_or_path=payload["backgroundImage"],
            canvas_json=payload["canvasJson"],
            layout_type=payload.get("layoutType", "default")
        )

        # updatedCanvas의 일부만 3줄 출력 (dump 후 잘라내기)
        try:
            import json
            preview = json.dumps(updated, ensure_ascii=False, indent=2).split("\n")[:3]
            print("🔍 [EditorAI] 결과 미리보기:")
            for line in preview:
                print("   ", line)
        except Exception as e:
            print("❌ 미리보기 출력 실패:", e)

        return {
            "status": "success",
            "updatedCanvas": updated
        }
    except Exception as e:
        print(f"❌ [EditorAI] 에러 발생: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e),
            "updatedCanvas": None
        }
