import os
import uuid
import replicate
import requests
import asyncio
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# ✅ [모델 설정]
# 1. 영상 생성 모델 (Video): 24fps 고정, 인물 움직임 특화
VIDEO_MODEL = "bytedance/seedance-1-pro-fast"
# 2. 이미지 생성 모델 (Image): 16:9 배경 생성용 (Flux-Schnell: 빠르고 고화질)
IMAGE_MODEL = "black-forest-labs/flux-schnell"

# ✅ [프롬프트 매직 명령어]
# 고화질, 시네마틱한 연출을 위한 필수 키워드들
MAGIC_SUFFIX = ", static camera, full frame, no zoom, high quality, 4k, 8k, highly detailed, sharp focus, cinematic lighting"
NEGATIVE_PROMPT = "background, border, frame, distorted, morphing, zooming out, camera movement, blur, pixelated, low resolution, text, watermark"

async def generate_live_poster_service(request):
    """
    [하이브리드 생성 서비스]
    1. 9:16 요청 -> 원본 포스터 이미지 그대로 사용 (Image-to-Video)
    2. 16:9 요청 -> 기획 의도(Prompt)대로 16:9 이미지를 새로 생성 후 영상화 (Gen-then-Animate)
       -> 이렇게 해야 배경이 잘리지 않고 꽉 찬 16:9 고화질 영상이 나옵니다.
    """
    
    common_task_id = str(uuid.uuid4())
    print(f"🎬 [LivePoster] 생성 시작... Project: {request.project_id}")

    # 1. Motion Prompt 구성 (기획 의도 + 시각적 키워드 + 매직어)
    base_prompt = f"A cinematic poster based on '{request.concept_text}'. " \
                  f"Visual elements: {request.visual_keywords}. " \
                  f"Dramatic and atmospheric." 
    
    final_prompt = f"{base_prompt}{MAGIC_SUFFIX}"
    print(f"ℹ️ 적용 프롬프트: {final_prompt}")

    # 저장 디렉토리 설정
    save_dir = f"final_project/M{request.project_id}/live" 
    os.makedirs(save_dir, exist_ok=True)

    # 생성할 목표 비율 리스트
    targets = ["9:16", "16:9"]
    generated_results = []

    try:
        for ratio in targets:
            print(f"\n🔄 비율 [{ratio}] 처리 시작...")
            
            # 기본적으로 원본 이미지를 소스로 설정
            source_image_path = request.poster_image_path
            
            # ✅ [핵심 로직] 16:9 요청일 경우 -> 16:9 이미지를 새로 그립니다.
            if ratio == "16:9":
                print(f"🎨 16:9 비율에 맞는 새로운 베이스 이미지 생성 중... (Flux 모델)")
                try:
                    # Text-to-Image 생성 요청
                    image_output = replicate.run(
                        IMAGE_MODEL,
                        input={
                            "prompt": final_prompt,  # 같은 프롬프트 사용 -> 테마 통일
                            "aspect_ratio": "16:9",  # 16:9 비율 강제
                            "go_fast": True,
                            "megapixels": "1"
                        }
                    )
                    
                    # 생성된 이미지 URL 추출 (Flux는 리스트로 반환)
                    img_url = str(image_output[0]) if isinstance(image_output, list) else str(image_output)
                    
                    # 임시 파일로 저장
                    temp_img_name = f"temp_base_{common_task_id}_16x9.png"
                    temp_img_path = os.path.join(save_dir, temp_img_name)
                    
                    img_res = requests.get(img_url)
                    if img_res.status_code == 200:
                        with open(temp_img_path, 'wb') as f:
                            f.write(img_res.content)
                        source_image_path = temp_img_path # 소스 이미지를 방금 만든 걸로 교체!
                        print(f"✅ 16:9 베이스 이미지 준비 완료: {temp_img_path}")
                    else:
                        print("⚠️ 이미지 생성 실패, 부득이하게 원본 사용 (잘릴 수 있음)")
                
                except Exception as img_e:
                    print(f"⚠️ 이미지 생성 중 오류(원본 사용): {img_e}")
                    # 실패하면 원본 사용 (프로세스가 죽지 않도록 방어)

            # ---------------------------------------------------------
            # 2. 영상 생성 (Image-to-Video)
            # ---------------------------------------------------------
            if not os.path.exists(source_image_path):
                print(f"❌ 소스 파일 없음: {source_image_path}")
                continue

            print(f"📹 영상 생성 요청 (Source: {os.path.basename(source_image_path)})")
            
            # 파일을 열어서 AI에게 전송
            with open(source_image_path, "rb") as file:
                output = replicate.run(
                    VIDEO_MODEL,
                    input={
                        "image": file,              # (9:16 원본 or 생성된 16:9 이미지)
                        "prompt": final_prompt,     
                        "negative_prompt": NEGATIVE_PROMPT,
                        "resolution": "1080p",      
                        "aspect_ratio": ratio,      # 16:9 or 9:16
                        "duration": 5,
                        "fps": 24                   # ✅ 모델 스펙 준수 (24fps 고정)
                    }
                )
            
            # 결과 URL 처리
            video_url = str(output[0]) if isinstance(output, list) else str(output)
            
            # 영상 파일 저장
            ratio_safename = ratio.replace(":", "x")
            file_name = f"live_{common_task_id}_{ratio_safename}.mp4"
            local_file_path = os.path.join(save_dir, file_name)

            response = requests.get(video_url)
            if response.status_code == 200:
                with open(local_file_path, 'wb') as f:
                    f.write(response.content)
                print(f"💾 영상 저장 완료: {local_file_path}")
                
                # 결과 리스트에 추가
                generated_results.append({
                    "task_id": common_task_id,
                    "aspect_ratio": ratio,
                    "file_path": local_file_path,
                    "motion_prompt": final_prompt
                })
            else:
                raise Exception(f"영상 다운로드 실패: {response.status_code}")

    except Exception as e:
        print(f"❌ 프로세스 중 오류: {e}")
        raise e

    # 최종 결과 반환 (List 형태)
    return generated_results