import os
import replicate
import requests
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# 1. 🌐 [프롬프트 번역기] - OpenAI 버전과 동일한 함수명과 input/output
def translate_to_english(raw_prompt, title_k, date_k, location_k):
    """
    원본과 동일한 함수 signature 유지!
    Nano Banana Pro는 한글 텍스트를 직접 렌더링할 수 있으므로,
    한글 정보를 포함한 프롬프트를 만듭니다.
    """
    print(f"  [image_generator] Nano Banana Pro용 프롬프트 구성 중 (한글 포함)...")
    
    # 텍스트 정보 구성
    text_parts = []
    if title_k:
        text_parts.append(f"제목: '{title_k}'")
    if date_k:
        text_parts.append(f"날짜: '{date_k}'")
    if location_k:
        text_parts.append(f"장소: '{location_k}'")
    
    # Nano Banana Pro는 텍스트 렌더링이 강력하므로 명확하게 지시
    if text_parts:
        text_instruction = ", ".join(text_parts)
        final_prompt = f"중요: 영어는 절대 사용하지 말고 한글만 사용하세요. {raw_prompt}. 한글 타이포그래피를 포스터의 핵심 디자인 요소로 만들어주세요: {text_instruction}. 글자는 창의적이고 예술적으로 배치하고, 폰트 스타일은 축제 분위기와 완벽하게 조화를 이루며, 입체감과 장식 효과를 추가하세요. 텍스트가 이미지와 자연스럽게 통합되어 하나의 예술작품처럼 보여야 합니다. 고품질, 상세함, 8K, 전문적인 축제 포스터 디자인."
    else:
        final_prompt = f"중요: 영어는 절대 사용하지 말고 한글만 사용하세요. {raw_prompt}. 한글 타이포그래피를 포함한다면 포스터의 핵심 디자인 요소로 만들고, 창의적이고 예술적으로 배치하세요. 입체감과 장식 효과를 추가하여 하나의 예술작품처럼 보여야 합니다. 고품질, 상세함, 8K, 전문적인 축제 포스터 디자인."
    print(f"    👉 최종 프롬프트: {final_prompt[:100]}...")
    return final_prompt  # ✅ 원본과 동일: 문자열 반환


# 2. 🎨 [이미지 생성기] - OpenAI 버전과 동일한 함수명과 input/output
def generate_image_dalle3(prompt, width, height, output_path):
    """
    원본과 동일한 함수 signature 유지!
    내부만 DALL-E 3 → Nano Banana Pro로 변경
    """
    print(f"  [Nano Banana Pro] 생성 요청 시작 (크기: {width}x{height})...")
    
    try:
        # 🔑 Replicate API 토큰 확인
        api_token = os.getenv("REPLICATE_API_TOKEN")
        if not api_token:
            print("    🚨 오류: REPLICATE_API_TOKEN이 환경변수에 없습니다.")
            return {"error": "REPLICATE_API_TOKEN missing"}
        
        # 🤖 Google Nano Banana Pro 모델
        model_id = "google/nano-banana-pro"
        aspect_ratio = "3:4"  # 세로형 포스터 비율
        
        # Replicate API 실행
        print(f"    🎨 모델 실행 중... (aspect_ratio: {aspect_ratio})")
        output = replicate.run(
            model_id,
            input={
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,  # Nano Banana Pro는 aspect_ratio 사용
                "output_format": "png",
                "output_quality": 90,
                "num_outputs": 1
            }
                )
        
        # 결과 처리 - FileOutput 객체 직접 처리 (리스트가 아님!)
        if output:
            print(f"    ✅ [Nano Banana Pro] 이미지 생성 완료")
            
            # FileOutput을 직접 읽어서 저장
            with open(output_path, 'wb') as f:
                f.write(output.read())
            
            print(f"    💾 이미지 저장 완료: {output_path}")
            
            # ✅ 원본과 동일한 반환 형식
            return {"status": "success", "file_path": output_path}
        else:
            raise Exception("이미지 생성 결과가 없습니다.")
    
    except Exception as e:
        print(f"    ❌ [Error] Nano Banana Pro 생성 실패: {e}")
        # ✅ 원본과 동일한 에러 반환 형식
        return {"error": str(e)}