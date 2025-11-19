import os
import json
from fastapi import APIRouter, Form, File, UploadFile, HTTPException
from app.domain.poster import poster_model as models

try:
    from app.tools import pdf_tools           
    from app.service.poster import poster_generator    
    from app.service.poster import trend_analyzer      
    from app.service.poster import image_generator 
except ImportError as e:
    print(f"🚨 모듈 import 실패: {e}")
    exit()

# 🚨 [핵심] Java가 보내는 주소와 맞추기 위해 prefix를 비웁니다.
router = APIRouter(prefix="", tags=["Project Poster Generation"])
SAVE_DIR = r"C:\final_project\ACC\acc-ai\홍보물"

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# [API 1] Analyze
@router.post("/analyze/proposal")
async def handle_analysis_request(theme: str = Form(...), keywords: str = Form(...), title: str = Form(...), file: UploadFile = File(...)):
    print("\n--- [FastAPI 서버] /analyze/proposal 요청 수신 ---")
    try:
        _, ext = os.path.splitext(file.filename)
        temp_path = f"temp_upload{ext}"
        with open(temp_path, "wb") as f:
            f.write(await file.read())
            
        pdf_data = pdf_tools.analyze_pdf(temp_path)
        if os.path.exists(temp_path): os.remove(temp_path)
        
        return {
            "status": "success",
            "analysis_summary": pdf_data,
            "poster_trend_report": {"status": "success"},
            "strategy_report": {"strategy_text": "Strategy...", "proposed_content": {}}
        }
    except Exception as e:
        print(f"🚨 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# [API 2] Generate Prompt (규격 선택 기능 복구)
@router.post("/generate-prompt")
async def handle_prompt_generation(body: models.GeneratePromptRequest):
    print("\n--- [FastAPI 서버] /generate-prompt 요청 수신 ---")
    try:
        # poster_generator가 { "prompt_options_data": ... } 형태가 아닌 순수 데이터를 반환하도록 조정
        result = poster_generator.create_master_prompt(
            body.theme, body.analysis_summary, body.poster_trend_report, body.strategy_report, body.selected_formats
        )
        
        # Java/프론트엔드가 기대하는 형태로 감싸서 반환
        return {"status": "success", "prompt_options_data": result}
    except Exception as e:
        print(f"🚨 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# [API 3] Create Image (Flux)
@router.post("/create-image")
async def handle_image_creation(body: models.CreateImageRequest):
    print("\n--- [FastAPI 서버] /create-image 요청 수신 ---")
    try:
        selected_data = body.selected_prompt
        
        # 1. 프롬프트 번역
        raw_prompt = selected_data.visual_prompt_for_background
        final_prompt = image_generator.translate_to_english(raw_prompt)
        
        # 2. 규격 (선택된 옵션의 사이즈 사용)
        width = selected_data.width
        height = selected_data.height
        
        final_filename = f"flux_{width}x{height}.png"
        final_filepath = os.path.join(SAVE_DIR, final_filename)
        
        # 3. 이미지 생성
        result = image_generator.generate_image_replicate(
            prompt=final_prompt,
            width=width,
            height=height,
            output_path=final_filepath
        )

        if "error" in result:
            raise Exception(result['error'])

        image_url = f"/poster-images/{final_filename}"

        return {
            "status": "success",
            "image_url": image_url,
            "text_data": body.analysis_summary,
            "style_guide": f"Flux Generated (Style: {selected_data.style_name})"
        }
    except Exception as e:
        print(f"🚨 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))