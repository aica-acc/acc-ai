import os
import time
import base64
import requests # 다운로드를 위해 requests 라이브러리 추가
from google import genai
from google.genai import types
from dotenv import load_dotenv
from pathlib import Path

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# 환경설정 
api_key = os.getenv("GEMINI_API_KEY")
MODEL = "veo-3.1-generate-preview" # Veo 3.1 모델 이름

# requests 라이브러리에서 API 키를 사용하기 위해 전역에서 정의


try:
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경 변수가 설정되지 않았거나 .env 파일에 없습니다.")
        
    client = genai.Client(api_key=api_key)
    print("✅ Veo 3.1 API 클라이언트가 .env를 통해 성공적으로 초기화되었습니다.")
    
except ValueError as ve:
    print(f"클라이언트 초기화 오류: {ve}")
    print("API 키가 `.env` 파일에 `GEMINI_API_KEY='YOUR_KEY'` 형식으로 올바르게 설정되었는지 확인해주세요.")
    exit()
except Exception as e:
    print(f"클라이언트 초기화 오류: {e}")
    print("API 키가 올바른 형식인지, 라이브러리가 최신 버전인지 확인해주세요.")
    exit()


def wait_for_operation(operation):
    """비동기 작업이 완료될 때까지 기다리는 헬퍼 함수"""
    while not operation.done:
        print("⏳ 비디오 생성 대기 중... (10초 후 재확인)")
        time.sleep(10)
        operation = client.operations.get(operation)

    if operation.error:
        print(f"❌ 비디오 생성 실패: {operation.error}")
        return None
    else:
        video_result = operation.result.generated_videos[0]
        video_uri = video_result.video.uri 
        print(f"✅ 비디오 생성 완료! 결과 URI: {video_uri}") 
        return video_result


# 🚨 FIX: requests 기반으로 다운로드 함수를 변경하여 SDK 오류를 우회합니다.
def download_video(video_file, output_filename: str):
    """
    requests 라이브러리를 사용하여 비디오 URI에서 직접 다운로드합니다.
    """
    DOWNLOAD_DIR = Path("generated_videos")
    DOWNLOAD_DIR.mkdir(exist_ok=True) 

    output_path = DOWNLOAD_DIR / output_filename
    
    # GeneratedVideo 객체에서 URI 추출
    video_uri = video_file.video.uri
    
    # API 키를 URI에 추가하여 인증
    global api_key
    download_url = f"{video_uri}&key={api_key}" if 'key=' not in video_uri else video_uri
        
    try:
        # requests.get을 사용하여 스트림 방식으로 다운로드
        response = requests.get(download_url, stream=True)
        response.raise_for_status() # HTTP 오류 검사
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        print(f"⬇️ 비디오 다운로드 완료: {output_path.resolve()}")
        return True
    except Exception as e:
        print(f"❌ 비디오 다운로드 실패 (requests 오류): {e}")
        print("URI가 만료되었거나, 네트워크 문제일 수 있습니다.")
        return False

def _read_and_encode_image(image_path: str) -> types.Image:
    """로컬 이미지를 읽어 Base64로 인코딩하고 types.Image 객체로 반환합니다."""
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"이미지 파일이 존재하지 않습니다: {image_path}")
    
    mime_type = "image/jpeg"
    if image_path.suffix.lower() == ".png":
        mime_type = "image/png"

    with open(image_path, "rb") as f:
        image_bytes = f.read()
    
    base64_encoded_data = base64.b64encode(image_bytes).decode('utf-8')
    
    return types.Image(
        image_bytes=base64_encoded_data,
        mime_type=mime_type
    )

def generate_image_to_video(prompt: str, start_image_path: str, end_image_path: str = None, download_name: str = "image_to_video.mp4"):
    """
    Veo 3.1을 사용하여 이미지 기반 비디오를 생성하고 다운로드합니다.
    """
    print(f"\n--- 1. Image to Video 시작 (프롬프트: {prompt[:30]}...) ---")
    
    start_frame_image = None
    last_frame_image = None
    
    try:
        start_frame_image = _read_and_encode_image(start_image_path)
        print(f"✅ 시작 이미지 Base64 인코딩 완료: {start_image_path}")

        if end_image_path:
            last_frame_image = _read_and_encode_image(end_image_path)
            print(f"✅ 끝 이미지 Base64 인코딩 완료: {end_image_path}")

    except FileNotFoundError as e:
        print(f"❌ 파일 처리 중 오류 발생: {e}")
        return None
    except Exception as e:
        print(f"❌ 이미지 인코딩 중 오류 발생: {e}")
        return None

    config_params = {}
    if last_frame_image:
        config_params["last_frame"] = last_frame_image
    
    video_config = types.GenerateVideosConfig(**config_params) if config_params else None

    # 3. 비디오 생성 요청
    operation = client.models.generate_videos(
        model=MODEL,
        prompt=prompt,
        image=start_frame_image,
        config=video_config,
    )
    
    # 4. 비동기 작업 대기 및 결과 처리
    result_video = wait_for_operation(operation)

    # 5. 다운로드
    if result_video:
        download_video(result_video, download_name)
        
    return result_video


def generate_text_to_video(prompt: str, download_name: str = "text_to_video.mp4"):
    """
    Veo 3.1을 사용하여 텍스트 프롬프트 기반으로 비디오를 생성하고 다운로드합니다.
    """
    print(f"\n--- 2. Text to Video 시작 (프롬프트: {prompt[:30]}...) ---")
    
    # 1. 비디오 생성 요청
    operation = client.models.generate_videos(
        model=MODEL,
        prompt=prompt,
        config=None,
    )
    
    # 2. 비동기 작업 대기 및 결과 처리
    result_video = wait_for_operation(operation)

    # 3. 다운로드
    if result_video:
        download_video(result_video, download_name)
        
    return result_video


def extend_video(existing_video, extension_prompt: str, download_name: str = "extended_video.mp4"):
    """
    기존 Veo 비디오를 확장하여 새로운 클립을 생성하고 다운로드합니다.
    """
    if not existing_video:
        print("❌ 확장할 기존 비디오가 없습니다. 이전 단계의 비디오 객체가 필요합니다.")
        return

    print(f"\n--- 3. Extension (비디오 확장) 시작 ---")
    
    video_uri = existing_video.video.uri
    print(f"기존 비디오 URI: {video_uri}")
    print(f"확장 프롬프트: {extension_prompt}")
    
    # 1. 비디오 확장 요청
    operation = client.models.generate_videos(
        model=MODEL,
        prompt=extension_prompt,
        video=existing_video,
        config=None,
    )
    
    # 2. 비동기 작업 대기 및 결과 처리
    result_video = wait_for_operation(operation)

    # 3. 다운로드
    if result_video:
        download_video(result_video, download_name)
        
    return result_video


# --- 스크립트 실행 예시 ---
if __name__ == "__main__":
    
    # 🚨 주의: 아래 경로들을 실제 파일 경로로 수정하세요. (파일명 포함!)
    BASE_DIR = str(Path(__file__).resolve().parent / 'test_images')
    START_IMAGE_PATH = str(Path(BASE_DIR) / "test.png") 
    END_IMAGE_PATH = str(Path(BASE_DIR) / "end_frame.jpg") 
    
    if not Path(START_IMAGE_PATH).exists():
        print(f"\n⚠️ 경고: 시작 이미지 파일이 존재하지 않습니다. 경로를 확인하세요: {START_IMAGE_PATH}")

    print("-" * 50)
    print("Veo 3.1 API 기능 테스트 시작 (Requests 다운로드 적용)")
    print("-" * 50)

    # 1. Image-to-Video (시작 프레임만 사용)
    prompt_text = """Create an 8-second motion teaser from this poster image.

    0–4 seconds:
    - Perform a cinematic zoom *into* the center neon circle portal, simulating depth and camera dive (not simple 2D scale).

    4–8 seconds:
    - STOP all further zooming completely.
    - HOLD the camera at the portal-entry distance (roughly the depth shown in the first reference image, not deeper).
    - Keep the world steady with only very subtle portal rotation and light pulse.
    - Animate the crowd silhouettes into a joyful neon dance party, slightly staggered in motion timing to feel like live festival characters inside the world.

    Rules:
    - No continuous inward zoom after 4s.
    - Do NOT flatten or move deeper than the first-image depth.
    - Maintain neon blue/orange/mint festival aesthetics.
    - No text animation or added objects.
    """

    video_1 = generate_image_to_video(
        prompt=prompt_text,
        start_image_path=START_IMAGE_PATH,
        end_image_path=None, # last_frame 생략
        download_name="02_image_only.mp4"
    )
    
    # 🚨 비용 절감을 위해 나머지 테스트는 임시로 주석 처리합니다.
    
    # # 2. Image-to-Video (Frame-to-Frame 전환)
    # print("\n[테스트 2: Frame-to-Frame 전환]")
    # generate_image_to_video(
    #     prompt="해질 녘부터 밤하늘로 극적으로 바뀌는 고속 전환 효과",
    #     start_image_path=START_IMAGE_PATH,
    #     end_image_path=END_IMAGE_PATH, # last_frame 사용
    #     download_name="02_frame_to_frame.mp4"
    # )

    # # 3. Text-to-Video (확장을 위해 저장)
    # print("\n[테스트 3: Text-to-Video]")
    # initial_video_for_extension = generate_text_to_video(
    #     prompt="안개 낀 아침, 작은 오두막 문 앞에 서 있는 붉은색 여우 한 마리. 슬로우 줌인.",
    #     download_name="03_initial_text_video.mp4"
    # )

    # # 4. Extension (비디오 확장)
    if video_1:
        print("\n[테스트 4: Video Extension]")
        extend_video(
            existing_video=video_1,
            extension_prompt=
            """Create an 8-second motion teaser from this poster image.
            0–6s:
            - (Already implemented by model) Animate poster silhouettes grooving and dancing playfully inside the neon portal world.
            - No further instructions for this segment.

            6–8s (Text Throw & Return):
            - At 6s, a glowing Santa character throws a 3D text:  
                "FESTIVAL COMING SOON"
            - The text travels *outward toward the viewer* (not inward/deeper).
            - It should feel like being *recalled from a distant 3D space* using motion-momentum easing and slight 3D spin/rotation while flying forward.
            - Camera must remain almost steady (no zoom-in after 6s).

            Landing (7.5–8s):
            - The text card SLAMS onto the screen with a 0.3–0.5s bright white flash, then stabilizes crisply for easy reading.
            - When stabilized, the text card should NOT be flat; it must:
            - Have a slight tilt angle (e.g., 6°–10°),
            - Appear like a 3D motion-graphics text card, easy to read but not axis-aligned,
            - Hold that tilt without extra animation after landing.

            Visual integrity:
            - Maintain original poster neon aesthetics (blue/orange/mint glow palette).
            - No added objects except the thrown text card.
            - No text animation other than throw → forward flight → slam → hold tilt.
            """,
            download_name="04_extended_video.mp4"
        )