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

        result = mascot_generator.create_mascot_images(body.prompt_options, batch=body.batch)

        if result.get("status") != "success":
            msg = result.get("error") or "Mascot image generation failed"
            print(f"[Mascot] 이미지 생성 실패: {msg}")
            # 외부 모델 실패라 502. 성공한 장은 batch 폴더에 남아 다시 요청하면 실패한 장만 만든다 (#31)
            raise HTTPException(status_code=502, detail={
                "message": msg,
                "failed": result.get("failed", []),
                "succeeded": result.get("succeeded", []),
            })

        return {
            "status": "success",
            "images": result["images"],
        }

    except HTTPException:
        raise

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        print(f"[Mascot] 이미지 생성 예외: {e}")
        raise HTTPException(status_code=500, detail=str(e))
