import os
import replicate
import requests
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# 1. 🌐 [프롬프트 번역기 및 최적화]
def translate_to_english(raw_prompt, title_k, date_k, location_k):
    """
    Nano Banana Pro 모델을 위한 최적화된 프롬프트 생성 (High-End 2D Style)
    """
    print(f"  [image_generator] Nano Banana Pro용 프롬프트 고도화 중 (Quality & No-3D)...")
    
    # 텍스트 정보 구성
    text_parts = []
    if title_k:
        text_parts.append(f"제목: '{title_k}'")
    if date_k:
        text_parts.append(f"날짜: '{date_k}'")
    if location_k:
        text_parts.append(f"장소: '{location_k}'")
    
    # ✅ [1] 스타일/퀄리티 부스터 (영어로 강력하게 선언)
    quality_prefix = (
        "Masterpiece, best quality, high resolution, 8k, "
        "professional commercial festival poster, flat 2D illustration, "
        "vector art style, clean lines, vibrant colors, "
        "perfect composition, trending on ArtStation. "
    )

    # ✅ [2] 한글 텍스트 지시 (사용자님 의도 반영)
    if text_parts:
        text_instruction = ", ".join(text_parts)
        content_prompt = (
            f"IMPORTANT: Use KOREAN text ONLY. No English text. {raw_prompt}. "
            f"한글 타이포그래피를 포스터의 핵심 디자인 요소로 만들어주세요: {text_instruction}. "
            f"글자는 창의적이고 예술적으로 배치하되, 전체 포스터의 15-20% 크기로 작고 세련되게 배치하세요. "
            f"텍스트가 이미지와 자연스럽게 통합되어 하나의 예술작품처럼 보여야 합니다. "
            f"고품질, 상세함, 8K, 전문적인 축제 포스터 디자인."
        )
    else:
        content_prompt = (
            f"IMPORTANT: Use KOREAN text ONLY. No English text. {raw_prompt}. "
            f"한글 타이포그래피를 포함한다면 포스터의 핵심 디자인 요소로 만들고, "
            f"전체 포스터의 15% 정도로 작고 세련되게 배치하세요. "
            f"입체감보다는 평면적인 아트웍 느낌을 강조하세요. "
            f"고품질, 상세함, 8K, 전문적인 축제 포스터 디자인."
        )

    # ✅ [3] 부정 프롬프트 (3D, 저퀄리티, 큰 글씨 방지)
    negative_suffix = (
        "Avoid: 3d render, cgi, plastic, clay, realistic photo, "
        "blurry, distorted, low quality, watermark, "
        "oversized text, messy text, cut off, ugly face, bad anatomy."
    )

    # 최종 합체
    final_prompt = f"{quality_prefix} {content_prompt} {negative_suffix}"
    
    print(f"    👉 최종 프롬프트: {final_prompt[:100]}...")
    return final_prompt


# 2. 🎨 [이미지 생성기]
def generate_image_dalle3(prompt, width, height, output_path):
    """
    Replicate의 Google Nano Banana Pro 모델 사용
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
                "aspect_ratio": aspect_ratio,
                "output_format": "png",
                "output_quality": 90,
                "num_outputs": 1
            }
        )
        
        # 결과 처리
        if output:
            print(f"    ✅ [Nano Banana Pro] 이미지 생성 완료")
            
            # FileOutput을 직접 읽어서 저장
            try:
                with open(output_path, 'wb') as f:
                    f.write(output.read())
            except AttributeError:
                # 만약 output이 URL 문자열 리스트라면 (가끔 바뀜)
                if isinstance(output, list):
                    image_url = output[0]
                    response = requests.get(image_url)
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                else:
                    # 단일 객체인 경우
                    with open(output_path, 'wb') as f:
                        f.write(output.read())

            print(f"    💾 이미지 저장 완료: {output_path}")
            
            return {
                "status": "success",
                "file_path": output_path
            }
        else:
            print("    ❌ 생성된 이미지가 없습니다.")
            return {"error": "No output from model"}

    except Exception as e:
        print(f"    🚨 이미지 생성 중 오류 발생: {e}")
        return {"error": str(e)}