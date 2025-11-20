import os
import json
import time
from fastapi import APIRouter, Form, File, UploadFile, HTTPException
from app.domain.poster import poster_model as models

try:
    from app.tools.proposal import pdf_tools           
    from app.service.poster import poster_generator    
    from app.service.poster import trend_analyzer      
    from app.service.poster import image_generator 
except ImportError as e:
    print(f"🚨 모듈 import 실패: {e}")
    exit()

router = APIRouter(prefix="", tags=["Project Poster Generation"])
SAVE_DIR = r"C:\final_project\ACC\acc-ai\홍보물"

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
    print("\n--- [FastAPI 서버] /create-image 요청 수신 (4종 일괄 생성) ---")
    try:
        analysis_data = body.analysis_summary
        prompt_options = body.prompt_options # 리스트 받음

        generated_results = []
        
        print(f"  🚀 총 {len(prompt_options)}개의 이미지 생성을 시작합니다...")

        for i, option in enumerate(prompt_options):
            style_name = option.style_name
            # 호환성: visual_prompt_for_background가 없으면 visual_prompt 사용
            raw_prompt = option.visual_prompt_for_background or option.visual_prompt
            text_content = option.text_content
            
            print(f"    👉 [{i+1}/{len(prompt_options)}] 스타일: {style_name} 생성 중...")

            # 1. 한글 텍스트 추출 (번역기에 전달용)
            title_k = ""
            date_k = ""
            location_k = ""
            
            if text_content:
                title_k = text_content.title
                date_k = text_content.date_location # 날짜+장소
            elif analysis_data: # text_content 없으면 분석 데이터에서 백업
                title_k = analysis_data.get("title", "")
                date_k = analysis_data.get("date", "")
                location_k = analysis_data.get("location", "")

            # 2. 프롬프트 번역 및 최적화 (영어 타이포그래피 포함)
            final_prompt = image_generator.translate_to_english(raw_prompt, title_k, date_k, location_k)
            
            # 3. 규격 설정 (세로형 고정)
            width = 1024
            height = 1792
            
            # 4. 파일명 생성
            timestamp = int(time.time())
            final_filename = f"poster_{timestamp}_{i}.png"
            final_filepath = os.path.join(SAVE_DIR, final_filename)
            
            # 5. DALL-E 3 이미지 생성 호출
            img_result = image_generator.generate_image_dalle3(
                prompt=final_prompt,
                width=width,
                height=height,
                output_path=final_filepath
            )
            
            image_url = ""
            if "status" in img_result and img_result["status"] == "success":
                image_url = f"/poster-images/{final_filename}"
            else:
                print(f"      ❌ 생성 실패: {img_result.get('error')}")

            # 결과 리스트에 추가
            generated_results.append({
                "style_name": style_name,
                "image_url": image_url,
                "visual_prompt": final_prompt,
                "text_content": text_content
            })

        print("  ✅ 모든 이미지 생성 완료!")

        return {
            "status": "success",
            "images": generated_results # 리스트 반환
        }

    except Exception as e:
        print(f"🚨 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
