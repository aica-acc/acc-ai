# image_generator.py (v29: '텍스트 없는' 배경 전용 생성기)

import os
from dotenv import load_dotenv
import requests
import io
from PIL import Image
import replicate # ⭐️ Replicate 라이브러리 (필수)

# ----------------------------------------------------
# 1. API 키 설정
# ----------------------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # (poster_generator.py용)

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
if not REPLICATE_API_TOKEN:
    print("[image_generator] REPLICATE_API_TOKEN을 .env 파일에서 찾을 수 없습니다.")
else:
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

# ----------------------------------------------------
# ⭐️ 3단계 최종 함수 (v29: '텍스트 없는' 배경 생성)
# ----------------------------------------------------
def create_background_image_v29(background_prompt, width, height, output_filename="background_v29.png"):
    """
    [v29] bytedance/dreamina-3.1 모델을 사용하여
    '텍스트 없는' 고품질 배경 이미지를 생성합니다.
    """
    print(f"  [image_generator] 3단계 '배경 이미지 생성' (v29 - Dreamina {width}x{height}) 시작...")
    
    if not REPLICATE_API_TOKEN:
        return {"error": "Replicate API 토큰이 설정되지 않았습니다."}
    if not background_prompt:
        return {"error": "Dreamina에 전달할 배경 프롬프트가 없습니다."}
        
    try:
        # --- (Step 1) Replicate 'Dreamina' 배경 생성 ---
        
        # ⭐️ [v29] 프롬프트에 'text-free'를 한 번 더 강조 (안전장치)
        final_prompt = f"{background_prompt}, no text, no letters, text-free, no writing, blank, empty"
        
        print(f"    - (1/2) Replicate (bytedance/dreamina-3.1) '배경' 호출 중...")
        
        dreamina_model_id = "bytedance/dreamina-3.1"
        
        output = replicate.run(
            dreamina_model_id,
            input={
                "prompt": final_prompt, # ⭐️ '텍스트 없는' 배경 프롬프트
                "width": width,
                "height": height,
                "aspect_ratio": "custom", 
                "negative_prompt": "text, letters, writing, signature, watermark, typography", # ⭐️ 텍스트 생성 강력히 방지
                "num_outputs": 1,
                "resolution": "2K" 
            }
        )
        
        # ⭐️ v22.1 버그 수정 적용 (단일 객체 반환)
        image_url = output
        if isinstance(output, list):
            image_url = output[0]
        
        print(f"    - (1/2) Replicate '배경' 이미지 다운로드 중...")
        image_response = requests.get(image_url)
        image_response.raise_for_status()
        
        final_image = Image.open(io.BytesIO(image_response.content))

        # --- (Step 2) 최종 파일 저장 ---
        save_path = os.path.join(os.path.dirname(__file__), output_filename)
        final_image.save(save_path)
        
        print(f"    - (2/2) '배경' 저장 완료! (경로: {save_path})")
        
        return {"status": "success", "image_path": save_path}

    except Exception as e:
        print(f"    ❌ 배경 이미지 생성 중 오류 발생: {e}")
        return {"error": f"Replicate API 오류 (v29): {e}"}

# ----------------------------------------------------
# (참고) v22.1 함수 - 이제 이 함수는 사용되지 않습니다.
# ----------------------------------------------------
def create_poster_image_v22(*args, **kwargs):
    print("  [image_generator] (v22.1 함수 호출됨 - v29로 업그레이드 필요)")
    return {"error": "v22.1 함수는 더 이상 사용되지 않습니다. v29를 호출하세요."}