import os
import uuid
import replicate
import requests
import asyncio
from typing import Dict, Any, List
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# ✅ [모델 설정]
VIDEO_MODEL = "bytedance/seedance-1-pro-fast"

# 프롬프트 매직 명령어
MAGIC_SUFFIX = ", static camera, full frame, no zoom, high quality, 4k, 8k, highly detailed, sharp focus, cinematic lighting"
NEGATIVE_PROMPT = "background, border, frame, distorted, morphing, zooming out, camera movement, blur, pixelated, low resolution, text, watermark"

# ✅ [표준 포맷 상수 정의]
LIVE_POSTER_TYPE = "live_poster"
LIVE_POSTER_NAME = "라이브 포스터"

async def generate_live_poster_service(request) -> List[Dict[str, Any]]:
    """
    [9:16 전용 생성 서비스 - 표준 포맷 적용]
    요청받은 원본 이미지를 9:16 영상으로 변환하고,
    공통 표준 Dict 포맷에 맞춰 결과를 반환합니다.
    """
    
    # 1. 공통 Task ID 생성
    common_task_id = str(uuid.uuid4())
    print(f"🎬 [LivePoster] 9:16 생성 시작... Project: {request.project_id}")

    # 2. Motion Prompt 구성
    base_prompt = (
        f"A cinematic poster based on '{request.concept_text}'. "
        f"Visual elements: {request.visual_keywords}. "
        f"Dramatic and atmospheric."
    )
    final_prompt = f"{base_prompt}{MAGIC_SUFFIX}"
    
    # 3. 저장 경로 설정 (상대 경로 사용)
    # 윈도우 호환성을 위해 os.path.join 사용
    save_dir = os.path.join("final_project", f"M{request.project_id}", "live")
    os.makedirs(save_dir, exist_ok=True)

    generated_results = []
    
    try:
        # ✅ 9:16 비율 고정
        target_ratio = "9:16"
        
        # 🚨 [테스트 모드] DB 경로 무시하고, 내 컴퓨터에 진짜 있는 파일로 강제 설정!
        source_image_path = "app/poster_service/poster_final_864x1152.png" 

        # 혹시 위 파일이 없으면 다른 걸로 시도 (안전장치)
        if not os.path.exists(source_image_path):
            print(f"⚠️ 테스트 파일도 못 찾아서, 요청받은 경로로 다시 시도합니다.")
            source_image_path = request.poster_image_path.strip().lstrip("/").lstrip("\\")
        
        if not os.path.exists(source_image_path):
            raise Exception(f"❌ 원본 파일이 없습니다: {source_image_path} (CWD: {os.getcwd()})")

        print(f"📹 [TEST] 영상 생성 요청 (Source: {source_image_path})")
        
        # 4. Replicate AI 호출
        with open(source_image_path, "rb") as file:
            output = replicate.run(
                VIDEO_MODEL,
                input={
                    "image": file,              
                    "prompt": final_prompt,     
                    "negative_prompt": NEGATIVE_PROMPT,
                    "resolution": "1080p",      
                    "aspect_ratio": target_ratio, # 9:16 고정
                    "duration": 5,
                    "fps": 24
                }
            )
        
        # 5. 결과 다운로드 및 저장
        video_url = str(output[0]) if isinstance(output, list) else str(output)
        
        file_name = f"live_{common_task_id}_9x16.mp4"
        local_file_path = os.path.join(save_dir, file_name)

        response = requests.get(video_url)
        if response.status_code == 200:
            with open(local_file_path, 'wb') as f:
                f.write(response.content)
            print(f"💾 영상 저장 완료: {local_file_path}")
            
            # ✅ [핵심] 표준 Dict 포맷 + 전용 데이터 통합
            db_save_path = local_file_path.replace("\\", "/")

            result_data: Dict[str, Any] = {
                # 1. 팀 공통 표준 필드
                "db_file_type": LIVE_POSTER_TYPE,
                "type": "video",
                "db_file_path": db_save_path,
                "type_ko": LIVE_POSTER_NAME,

                # 2. 라이브 포스터 전용 필드
                "task_id": common_task_id,
                "motion_prompt": final_prompt,
                "aspect_ratio": target_ratio,

                # 3. 자바 호환성 유지 필드
                "file_path": db_save_path 
            }
            
            generated_results.append(result_data)
            
        else:
            raise Exception(f"영상 다운로드 실패: {response.status_code}")

    except Exception as e:
        print(f"❌ 프로세스 중 오류: {e}")
        raise e

    # 리스트 형태로 반환
    return generated_results