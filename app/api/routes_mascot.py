from fastapi import APIRouter, HTTPException

from app.domain.poster import poster_model as models
from app.service.mascot import mascot_generator

router = APIRouter(prefix="", tags=["Mascot Generation"])


@router.post("/generate/mascot/prompt")
async def generate_prompt(body: models.GeneratePromptRequest):
    try:
        print("[Mascot] /generate-mascot-prompt 요청 수신")
        result = mascot_generator.create_mascot_prompt(
            user_theme=body.theme,
            analysis_summary=body.analysis_summary,
            poster_trend_report=body.poster_trend_report,
            strategy_report=body.strategy_report,
        )
        return {
            "status": "success",
            "prompt_options_data": result,
        }
    except Exception as e:
        print(f"[Mascot] Prompt 생성 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-mascot-image")
async def create_images(body: models.CreateImageRequest):
    try:
        print("[Mascot] /create-mascot-image 요청 수신")

        result = mascot_generator.create_mascot_images(body.prompt_options)

        if result.get("status") != "success":
            msg = result.get("error") or "Mascot image generation failed"
            print(f"[Mascot] 이미지 생성 실패: {msg}")
            raise HTTPException(status_code=500, detail=msg)

        return {
            "status": "success",
            "images": result["images"],
        }

    except HTTPException:
        raise

    except Exception as e:
        print(f"[Mascot] 이미지 생성 예외: {e}")
        raise HTTPException(status_code=500, detail=str(e))
