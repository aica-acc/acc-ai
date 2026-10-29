import os
import json
import time
from fastapi import APIRouter, Form, File, UploadFile, HTTPException
from app.domain.poster import poster_model as models
from pydantic import BaseModel
from app.service.poster import image_generator

try:
    from app.tools.proposal import pdf_tools           
    from app.service.poster import poster_generator    
    from app.service.poster import trend_analyzer      
    from app.service.poster import image_generator 
except ImportError as e:
    print(f"🚨 모듈 import 실패: {e}")
    exit()

router = APIRouter(prefix="", tags=["Project Poster Generation"])
from app.core.config import PROMOTION_DIR
SAVE_DIR = str(PROMOTION_DIR / "poster")

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# [API 1] Analyze (기존 유지)
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

# [API 2] Generate Prompt (기존 유지 - 기획안 4개 생성)
@router.post("/generate-prompt")
async def handle_prompt_generation(body: models.GeneratePromptRequest):
    print("\n--- [FastAPI 서버] /generate-prompt 요청 수신 ---")
    try:
        result = poster_generator.create_master_prompt(
            body.theme, body.analysis_summary, body.poster_trend_report, body.strategy_report
        )
        return {"status": "success", "prompt_options_data": result}
    except Exception as e:
        print(f"🚨 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# [API 3] Create Image (🚨 4개 일괄 생성으로 업그레이드)
@router.post("/create-image")
async def handle_image_creation(body: models.CreateImageRequest):
    print("\n--- [FastAPI 서버] /create-image 요청 수신 (Replicate 버전) ---")
    try:
        analysis_data = body.analysis_summary
        prompt_options = body.prompt_options
        generated_results = []
        
        print(f"  🚀 총 {len(prompt_options)}개의 이미지 생성을 시작합니다...")

        for i, option in enumerate(prompt_options):
            style_name = option.style_name
            # 배경용 프롬프트 혹은 시각적 프롬프트 선택
            raw_prompt = option.visual_prompt_for_background or option.visual_prompt
            text_content = option.text_content
            
            # 1. 한글 텍스트 준비 
            title_k = ""
            date_k = ""
            location_k = ""
            
            if text_content:
                title_k = text_content.title
                date_k = text_content.date_location
            elif analysis_data:
                title_k = analysis_data.get("title", "")
                date_k = analysis_data.get("date", "")
                location_k = analysis_data.get("location", "")

            # 2. 파일명 및 경로 설정
            timestamp = int(time.time())
            final_filename = f"poster_{timestamp}_{i}.png"
            final_filepath = os.path.join(SAVE_DIR, final_filename)
            
            # 3. Replicate 이미지 생성 호출 (함수명 변경!)
           
            try:
                # 1단계: translate_to_english 함수로 프롬프트 생성
                final_prompt = image_generator.translate_to_english(
                    raw_prompt=raw_prompt,
                    title_k=title_k,
                    date_k=date_k,
                    location_k=location_k  # 장소도 포함!
                )
                
                # 2단계: 이미지 생성
                img_result = image_generator.generate_image_dalle3(
                    prompt=final_prompt,
                    width=896,
                    height=1152,
                    output_path=final_filepath
                )

                if "status" in img_result and img_result["status"] == "success":
                    # ✅ 실제 저장된 파일명만 반환
                    image_url = final_filename  # "/poster-images/" 제거!
                    print(f"      ✅ 생성 성공, 파일명: {final_filename}")
                else:
                    print(f"      ❌ 생성 실패: {img_result.get('error')}")
                    image_url = ""

                generated_results.append({
                    "style_name": style_name,
                    "image_url": image_url,  # 이제 파일명만 들어감
                    "file_name": final_filename,
                    "file_path": final_filepath,
                    "visual_prompt": raw_prompt,
                    "text_content": text_content
                })

            except Exception as inner_e:
                print(f"    ⚠️ 개별 생성 중 에러: {inner_e}")
                continue

        print("  ✅ 모든 이미지 생성 완료!")

        return {
            "status": "success",
            "images": generated_results
        }

    except Exception as e:
        print(f"🚨 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))
