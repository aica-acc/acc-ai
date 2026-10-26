import os
import time
import base64
import requests 
from google import genai
from google.genai import types
from dotenv import load_dotenv
from pathlib import Path
import subprocess # FFmpeg 호출을 위한 subprocess 모듈 추가

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


# requests 기반으로 다운로드 함수를 변경하여 SDK 오류를 우회합니다.
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
        return output_path # 다운로드된 파일 경로 반환
    except Exception as e:
        print(f"❌ 비디오 다운로드 실패 (requests 오류): {e}")
        print("URI가 만료되었거나, 네트워크 문제일 수 있습니다.")
        return None


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
        return None, None
    except Exception as e:
        print(f"❌ 이미지 인코딩 중 오류 발생: {e}")
        return None, None

    config_params = {}
    if last_frame_image:
        config_params["last_frame"] = last_frame_image
    
    # 여기서는 duration_s가 필요 없으므로 기존대로 GenerateVideosConfig를 사용합니다.
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
    download_path = None
    if result_video:
        download_path = download_video(result_video, download_name)
        
    return result_video, download_path


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
    download_path = None
    if result_video:
        download_path = download_video(result_video, download_name)
        
    return result_video, download_path


def extend_video(existing_video, extension_prompt: str, duration_s: int = 8, download_name: str = "extended_video.mp4"):
    """
    기존 Veo 비디오를 확장하여 새로운 클립을 생성하고 다운로드합니다.
    
    [핵심] Veo API는 'video' 매개변수에 기존 비디오 객체를 전달받으면 자동으로 확장 모드를 활성화합니다.
    주의: API는 '전체 연결된 영상'이 아닌, '새로 생성된 확장 클립'만을 반환합니다.
    """
    if not existing_video:
        print("❌ 확장할 기존 비디오가 없습니다. 이전 단계의 비디오 객체가 필요합니다.")
        return None, None

    # duration_s 인수는 이제 프롬프트 길이를 로깅하는 용도로만 사용됨
    print(f"\n--- 3. Extension (비디오 확장) 시작, 길이: {duration_s}s (프롬프트 지침에 의존) ---")
    
    # GeneratedVideo 객체에서 URI를 가져오기 위해 기존대로 .video.uri 사용
    video_uri = existing_video.video.uri
    print(f"기존 비디오 URI: {video_uri}")
    print(f"확장 프롬프트: {extension_prompt}")
    
    # 1. Configuration: duration_s가 GenerateVideosConfig에 포함되지 않도록 빈 객체를 전달합니다.
    video_config = types.GenerateVideosConfig() 

    # 2. 비디오 확장 요청
    # 🚨 수정: 'duration_s'가 'client.models.generate_videos' 메서드에서 허용되지 않으므로 제거했습니다.
    # 길이는 이제 전적으로 'extension_prompt' (7초 명시)에 의존하여 모델이 결정합니다.
    operation = client.models.generate_videos(
        model=MODEL,
        prompt=extension_prompt,
        video=existing_video.video, 
        config=video_config, 
    )
    
    # 3. 비동기 작업 대기 및 결과 처리
    # 반환되는 result_video는 '새로 생성된 확장 클립'입니다.
    result_video = wait_for_operation(operation)

    # 4. 다운로드
    download_path = None
    if result_video:
        # 다운로드 후, 이 파일은 '기존 영상의 다음 부분'임을 기억해야 합니다.
        download_path = download_video(result_video, download_name)
        
    return result_video, download_path

def concatenate_videos(input_paths: list[Path], output_filename: str):
    """
    FFmpeg을 사용하여 여러 비디오 파일을 순서대로 이어 붙입니다.
    
    주의: 이 함수를 사용하려면 시스템에 FFmpeg이 설치되어 있어야 합니다.
    """
    print(f"\n--- 4. FFmpeg으로 비디오 연결 시작 ---")
    
    if not input_paths:
        print("❌ 연결할 입력 파일 경로가 없습니다.")
        return

    DOWNLOAD_DIR = Path("generated_videos")
    output_path = DOWNLOAD_DIR / output_filename
    
    # FFmpeg의 concat 필터는 파일 목록이 필요합니다. 
    # 임시 목록 파일을 생성합니다.
    list_file_path = DOWNLOAD_DIR / "file_list.txt"
    with open(list_file_path, "w") as f:
        for path in input_paths:
            f.write(f"file '{path.name}'\n")

    # FFmpeg 명령 구성
    # -f concat: concat 파일 형식을 사용
    # -safe 0: 파일 경로의 안전성 검사를 해제 (간편한 실행을 위해)
    # -i {list_file_path}: 입력 파일 목록
    # -c copy: 인코딩 없이 스트림만 복사하여 빠르게 연결
    # -y: 덮어쓰기 허용
    ffmpeg_command = [
        "ffmpeg", 
        "-f", "concat", 
        "-safe", "0", 
        "-i", str(list_file_path), 
        "-c", "copy", 
        "-y",
        str(output_path)
    ]
    
    try:
        # FFmpeg 실행
        subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
        print(f"✅ 비디오 연결 완료: {output_path.resolve()}")
        # 임시 목록 파일 삭제
        os.remove(list_file_path)
        return output_path
        
    except FileNotFoundError:
        print("❌ 오류: 'ffmpeg' 명령을 찾을 수 없습니다. FFmpeg을 시스템에 설치하고 환경 변수(PATH)에 추가했는지 확인해주세요.")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg 실행 오류: 연결에 실패했습니다.")
        print(f"오류 메시지:\n{e.stderr}")
    except Exception as e:
        print(f"❌ 연결 중 알 수 없는 오류 발생: {e}")
    
    # 연결 실패 시 임시 파일 삭제
    if os.path.exists(list_file_path):
        os.remove(list_file_path)
        
    return None


# --- 스크립트 실행 예시 ---
if __name__ == "__main__":
    
    # 🚨 주의: 아래 경로들을 실제 파일 경로로 수정하세요. (파일명 포함!)
    BASE_DIR = str(Path(__file__).resolve().parent / 'test_images')
    START_IMAGE_PATH = str(Path(BASE_DIR) / "test2.png") 
    END_IMAGE_PATH = str(Path(BASE_DIR) / "end_frame.jpg") 
    
    if not Path(START_IMAGE_PATH).exists():
        print(f"\n⚠️ 경고: 시작 이미지 파일이 존재하지 않습니다. 경로를 확인하세요: {START_IMAGE_PATH}")

    print("-" * 50)
    print("Veo 3.1 API 기능 테스트 시작 (Requests 다운로드 적용)")
    print("-" * 50)

    # 연결할 파일 경로를 저장할 리스트
    segment_paths = []

    # 1. Image-to-Video (시작 프레임만 사용) - 첫 번째 8초 클립 생성
    prompt_text_1 = """Create an 8-second motion teaser from this poster image.

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

    video_1, path_1 = generate_image_to_video(
        prompt=prompt_text_1,
        start_image_path=START_IMAGE_PATH,
        end_image_path=None, # last_frame 생략
        download_name="01_segment_8s.mp4" # 파일명을 세그먼트임을 명확히 변경
    )
    if path_1:
        segment_paths.append(path_1)
    
    # 2. Extension (비디오 확장) - 두 번째 7초 클립 생성 (총 15초)
    if video_1:
        print("\n[테스트 2: Video Extension]")
        
        # 🚨 총 7초 분량의 확장 프롬프트 (8s + 7s = 15s)
        extension_prompt = """Continue the scene seamlessly from the previous 8-second clip.

        8–13s (5 seconds):
        - Seamlessly continue the motions of the portal rings, wireframe city, and shimmering trees.
        - Camera remains ABSOLUTELY steady, maintaining the existing poster's perspective.
        - Gradually brighten the portal glow over 5 seconds to build anticipation.

        13–15s (Final 2 seconds):
        - Santa (the figure closest to the camera) performs a natural welcoming gesture (arms opening forward).
        - A metallic, glowing 3D text card emerges from the portal center, flying forward toward the viewer with slight 3D rotation and motion-momentum easing.
        - The text must display exactly: "FESTIVAL COMING SOON"
        - At 14.7s: A 0.3s bright white flash/burst occurs.
        - The text stabilizes on screen at a readable size and holds a slight 3D tilt (6–10°).
        - No extra movement after the text lands."""
        
        video_2, path_2 = extend_video(
            existing_video=video_1,
            extension_prompt=extension_prompt,
            duration_s=8,  # <--- 이 값은 이제 로깅 용도로만 사용됩니다.
            download_name="02_extension_segment_7s.mp4" # 파일명 변경 (7s로)
        )
        if path_2:
            segment_paths.append(path_2)

    # 3. 두 클립을 FFmpeg으로 연결 (총 15초)
    if len(segment_paths) == 2:
        concatenate_videos(
            input_paths=segment_paths,
            output_filename="03_final_15s_concatenated.mp4" # 파일명 변경 (15s로)
        )