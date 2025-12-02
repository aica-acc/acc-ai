from fastapi import APIRouter, HTTPException
from app.domain.poster import poster_model as models
from app.service.mascot import mascot_generator

router = APIRouter(prefix="", tags=["Mascot Generation"])

# [API] Generate Mascot Prompt
@router.post("/generate/mascot/prompt")
async def handle_mascot_prompt_generation(body: models.GeneratePromptRequest):
    print("\n--- [FastAPI 서버] /generate/mascot/prompt 요청 수신 ---")
    try:
        result = mascot_generator.create_mascot_prompt(
            body.theme, body.analysis_summary, body.poster_trend_report, body.strategy_report
        )
        return {"status": "success", "prompt_options_data": result}
    except Exception as e:
        print(f"🚨 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))
