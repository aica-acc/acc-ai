from fastapi import APIRouter, HTTPException
from app.domain.poster import poster_model as models
from app.service.mascot import mascot_generator

router = APIRouter(prefix="", tags=["Mascot Generation"])

import os
import time
import openai
from app.service.poster import image_generator

# ===============================
# 🐻 마스코트 전용 영어 번역기
# ===============================
def translate_mascot_prompt(raw_prompt: str) -> str:
    system_instruction = """
    You are an expert translator for AI character generation.
    Your job is to translate Korean mascot descriptions into clean English
    WITHOUT adding any layout, poster, text, typography, or background instructions.
    
    Output must describe ONLY:
    - the mascot character
    - its outfit
    - its color palette
    - its pose and expression

    Forbidden:
    - poster
    - title
    - typography
    - layout
    - background
    - scenery
    - objects
    - props
    """

    client = openai.OpenAI()

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": raw_prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[⚠️ translate_mascot_prompt ERROR] {e}")
        return raw_prompt



# ============================================================
# [API] Generate Mascot Prompt
# ============================================================
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



# ============================================================
# ⭐ 마스코트 이미지 저장 폴더
# ============================================================
SAVE_DIR = r"C:\final_project\ACC\acc-ai\promotion\mascot"

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# ============================================================
# [API] Create Mascot Image
# ============================================================
@router.post("/create-mascot-image")
async def handle_mascot_image_creation(body: models.CreateImageRequest):
    print("\n--- [FastAPI 서버] /create-mascot-image 요청 수신 (4종 일괄 생성) ---")
    try:
        prompt_options = body.prompt_options

        generated_results = []
        
        print(f"  🚀 총 {len(prompt_options)}개의 마스코트 이미지 생성을 시작합니다...")

        for i, option in enumerate(prompt_options):
            style_name = option.style_name
            raw_prompt = option.visual_prompt_for_background or option.visual_prompt
            
            print(f"    👉 [{i+1}/{len(prompt_options)}] 스타일: {style_name} 생성 중...")

            # 1) 마스코트 전용 번역기 사용 (포스터 번역기 사용 절대 금지)
            translated_prompt = translate_mascot_prompt(raw_prompt)

            # 2) 마스코트 전용 프롬프트 빌더 적용
            final_prompt = mascot_generator.build_mascot_image_prompt(translated_prompt)
            
            # ⭐ 마스코트는 정사각형
            width = 1024
            height = 1024
            
            # 파일명 생성
            timestamp = int(time.time())
            final_filename = f"mascot_{timestamp}_{i}.png"
            final_filepath = os.path.join(SAVE_DIR, final_filename)
            
            # 3) DALL-E 3 이미지 생성
            img_result = image_generator.generate_image_dalle3(
                prompt=final_prompt,
                width=width,
                height=height,
                output_path=final_filepath
            )
            
            image_url = ""
            if "status" in img_result and img_result["status"] == "success":
                image_url = f"/poster-images/mascot/{final_filename}"
            else:
                print(f"      ❌ 생성 실패: {img_result.get('error')}")

            # 4) 포스터와 동일한 응답 구조로 반환
            generated_results.append({
                "style_name": style_name,
                "image_url": image_url,
                "file_name": final_filename,
                "file_path": final_filepath,
                "visual_prompt": final_prompt,
                "text_content": None
            })

        print("  ✅ 모든 마스코트 이미지 생성 완료!")

        return {
            "status": "success",
            "images": generated_results
        }

    except Exception as e:
        print(f"🚨 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))
