# app/service/poster/make_poster_video.py

import os
import time
import base64
import json
import io
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import OpenAI
from PIL import Image
import subprocess
from typing import Dict, List, Optional

load_dotenv()

# --------------------------------------------------
# 공통 설정
# --------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
...
FRONT_PROJECT_ROOT = os.getenv("FRONT_PROJECT_ROOT")
...
PROMOTION_CODE = "M000001"  # 고정값

load_dotenv()

# --------------------------------------------------
# 공통 설정
# --------------------------------------------------

PROJECT_ROOT = os.getenv("PROJECT_ROOT")
if not PROJECT_ROOT:
    raise ValueError("PROJECT_ROOT 가 .env에 설정되어 있지 않습니다.")
PROJECT_ROOT = Path(PROJECT_ROOT).resolve()

# 인트로 자막용 한글 폰트 (예: app/fonts/Jalnan2TTF.ttf)
INTRO_FONT_PATH = PROJECT_ROOT / "app" / "fonts" / "Jalnan2TTF.ttf"
if not INTRO_FONT_PATH.exists():
    raise FileNotFoundError(f"인트로 자막용 폰트 파일을 찾을 수 없습니다: {INTRO_FONT_PATH}")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY 가 .env에 설정되어 있지 않습니다.")


FRONT_PROJECT_ROOT = os.getenv("FRONT_PROJECT_ROOT")
if not FRONT_PROJECT_ROOT:
    raise ValueError("FRONT_PROJECT_ROOT 가 .env에 설정되어 있지 않습니다.")


veo_client = genai.Client(api_key=GEMINI_API_KEY)
openai_client = OpenAI()
VEO_MODEL = "veo-3.1-generate-preview"


# --------------------------------------------------
# Veo 헬퍼 (기존 로직 그대로 유지)
# --------------------------------------------------
def wait_for_operation(operation):
    """비동기 작업이 완료될 때까지 기다리는 헬퍼 함수"""
    while not operation.done:
        print("⏳ 비디오 생성 대기 중... (10초 후 재확인)")
        time.sleep(10)
        operation = veo_client.operations.get(operation)

    if operation.error:
        print(f"❌ 비디오 생성 실패: {operation.error}")
        return None
    else:
        video_result = operation.result.generated_videos[0]
        video_uri = video_result.video.uri
        print(f"✅ 비디오 생성 완료! 결과 URI: {video_uri}")
        return video_result


def download_video(video_file, output_filename: str) -> Optional[Path]:
    """
    requests 라이브러리를 사용하여 비디오 URI에서 직접 다운로드합니다.
    """
    DOWNLOAD_DIR = Path("generated_videos")
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    output_path = DOWNLOAD_DIR / output_filename
    video_uri = video_file.video.uri

    download_url = f"{video_uri}&key={GEMINI_API_KEY}" if "key=" not in video_uri else video_uri

    try:
        response = requests.get(download_url, stream=True)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"⬇️ 비디오 다운로드 완료: {output_path.resolve()}")
        return output_path
    except Exception as e:
        print(f"❌ 비디오 다운로드 실패 (requests 오류): {e}")
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

    base64_encoded_data = base64.b64encode(image_bytes).decode("utf-8")

    return types.Image(
        image_bytes=base64_encoded_data,
        mime_type=mime_type,
    )


def generate_image_to_video(
    prompt: str,
    start_image_path: str,
    end_image_path: str = None,
    download_name: str = "image_to_video.mp4",
) -> Tuple[Optional[Any], Optional[Path]]:
    """
    Veo 3.1을 사용하여 이미지 기반 비디오를 생성하고 다운로드합니다.
    """
    print(f"\n--- 1. Image to Video 시작 (프롬프트: {prompt[:60]}...) ---")

    try:
        start_frame_image = _read_and_encode_image(start_image_path)
        print(f"✅ 시작 이미지 Base64 인코딩 완료: {start_image_path}")

        last_frame_image = None
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

    video_config = types.GenerateVideosConfig(**config_params) if config_params else None

    operation = veo_client.models.generate_videos(
        model=VEO_MODEL,
        prompt=prompt,
        image=start_frame_image,
        config=video_config,
    )

    result_video = wait_for_operation(operation)

    download_path = None
    if result_video:
        download_path = download_video(result_video, download_name)

    return result_video, download_path


def extend_video(
    existing_video,
    extension_prompt: str,
    duration_s: int = 8,
    download_name: str = "extended_video.mp4",
) -> Tuple[Optional[Any], Optional[Path]]:
    """
    기존 Veo 비디오를 확장하여 새로운 클립을 생성하고 다운로드합니다.
    """
    if not existing_video:
        print("❌ 확장할 기존 비디오가 없습니다. 이전 단계의 비디오 객체가 필요합니다.")
        return None, None

    print(f"\n--- 3. Extension (비디오 확장) 시작, 길이: {duration_s}s ---")
    video_uri = existing_video.video.uri
    print(f"기존 비디오 URI: {video_uri}")
    print(f"확장 프롬프트: {extension_prompt[:80]}...")

    video_config = types.GenerateVideosConfig()

    operation = veo_client.models.generate_videos(
        model=VEO_MODEL,
        prompt=extension_prompt,
        video=existing_video.video,
        config=video_config,
    )

    result_video = wait_for_operation(operation)

    download_path = None
    if result_video:
        download_path = download_video(result_video, download_name)

    return result_video, download_path


def concatenate_videos(input_paths: list[Path], output_filename: str) -> Optional[Path]:
    """
    FFmpeg을 사용하여 여러 비디오 파일을 순서대로 이어 붙입니다.
    """
    print(f"\n--- 4. FFmpeg으로 비디오 연결 시작 ---")

    if not input_paths:
        print("❌ 연결할 입력 파일 경로가 없습니다.")
        return None

    DOWNLOAD_DIR = Path("generated_videos")
    output_path = DOWNLOAD_DIR / output_filename

    list_file_path = DOWNLOAD_DIR / "file_list.txt"
    with open(list_file_path, "w", encoding="utf-8") as f:
        for path in input_paths:
            f.write(f"file '{path.name}'\n")

    ffmpeg_command = [
        "ffmpeg",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file_path),
        "-c",
        "copy",
        "-y",
        str(output_path),
    ]

    try:
        subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
        print(f"✅ 비디오 연결 완료: {output_path.resolve()}")
        os.remove(list_file_path)
        return output_path
    except FileNotFoundError:
        print("❌ 오류: 'ffmpeg' 명령을 찾을 수 없습니다. FFmpeg PATH 설정 확인 필요.")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg 실행 오류: {e.stderr}")
    except Exception as e:
        print(f"❌ 연결 중 알 수 없는 오류 발생: {e}")

    if list_file_path.exists():
        os.remove(list_file_path)
    return None



# --------------------------------------------------
# FFmpeg / 인트로 관련 헬퍼
# --------------------------------------------------

def ffmpeg_escape_text(s: str) -> str:
    """
    ffmpeg drawtext용 텍스트 escape 헬퍼.
    - \, :, ' 정도만 처리
    """
    return (
        s.replace("\\", "\\\\")  # 역슬래시 → \\
         .replace(":", "\\:")    # 콜론 → \:
         .replace("'", "\\'")    # 작은따옴표 → \'
    )


def ffmpeg_escape_font_path(path: str) -> str:
    """
    drawtext fontfile용 경로 escape:
    - 백슬래시 → \\
    - 콜론 → \:
    """
    p = path.replace("\\", "\\\\")
    p = p.replace(":", "\\:")
    return p


def get_video_resolution(input_video: str, fallback=(1920, 1080)) -> tuple[int, int]:
    """
    ffprobe로 (width, height) 가져오되,
    실패하면 fallback 해상도(기본 1920x1080)를 리턴.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        input_video,
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )

    if proc.returncode != 0:
        print("⚠️ ffprobe 실패, fallback 해상도 사용:", fallback)
        print("ffprobe stderr:")
        print(proc.stderr)
        return fallback

    info = json.loads(proc.stdout)
    stream = info["streams"][0]
    return int(stream["width"]), int(stream["height"])


def create_black_intro_with_text(
    output_video: str,
    width: int,
    height: int,
    festival_name_ko: str,
    festival_period_ko: str,
    font_path: str,
    duration: float = 2.0,
    fps: int = 30,
    fontsize_title: int = 56,
    fontsize_period: int = 40,
) -> Path:
    """
    검정 배경 위에 축제명/기간 자막 2줄만 있는 인트로 영상 생성.
    """
    out_path = Path(output_video)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 텍스트 / 폰트 escape (add_intro_caption에서 쓰던 방식 재사용)
    fontfile = ffmpeg_escape_font_path(font_path)
    title_text = ffmpeg_escape_text(festival_name_ko)
    period_text = ffmpeg_escape_text(festival_period_ko)

    drawtext = (
        "drawtext="
        f"fontfile='{fontfile}':"
        f"text='{title_text}':"
        f"fontsize={fontsize_title}:"
        "fontcolor=white:"
        "box=1:boxcolor=black@0.5:boxborderw=20:"
        "x=(w-text_w)/2:"
        "y=(h/2)-50"
        ","
        "drawtext="
        f"fontfile='{fontfile}':"
        f"text='{period_text}':"
        f"fontsize={fontsize_period}:"
        "fontcolor=white:"
        "box=1:boxcolor=black@0.5:boxborderw=16:"
        "x=(w-text_w)/2:"
        "y=(h/2)+30"
    )

    cmd = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", f"color=c=black:s={width}x{height}:d={duration}:r={fps}",
        "-vf", drawtext,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-y",
        str(out_path),
    ]

    print("▶ ffmpeg (intro):")
    print(" ".join(cmd))
    print("  raw font_path =", font_path)
    print("  fontfile     =", fontfile)

    try:
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if completed.stderr:
            print("ffmpeg intro stderr (경고/로그):")
            print(completed.stderr)
    except subprocess.CalledProcessError as e:
        print("❌ ffmpeg intro 생성 실패")
        print("stdout:")
        print(e.stdout)
        print("stderr:")
        print(e.stderr)
        raise

    return out_path


def concat_intro_and_main(
    intro_video: str,
    main_video: str,
    output_video: str,
) -> Path:
    """
    인트로 영상(무음) + 본편 영상 을 하나로 이어붙이기.
    - 비디오 2개 concat
    - 오디오는 본편(두 번째 입력) 것을 그대로 사용
    """
    intro_path = Path(intro_video)
    main_path = Path(main_video)
    out_path = Path(output_video)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not intro_path.exists():
        raise FileNotFoundError(f"intro 없음: {intro_path}")
    if not main_path.exists():
        raise FileNotFoundError(f"main 없음: {main_path}")

    cmd = [
        "ffmpeg",
        "-i", str(intro_path),
        "-i", str(main_path),
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map", "[v]",
        "-map", "1:a?",   # 본편에 오디오 있으면 복사, 없으면 무시
        "-c:v", "libx264",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        "-y",
        str(out_path),
    ]

    print("▶ ffmpeg (concat intro+main):")
    print(" ".join(cmd))

    try:
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if completed.stderr:
            print("ffmpeg concat stderr (경고/로그):")
            print(completed.stderr)
    except subprocess.CalledProcessError as e:
        print("❌ ffmpeg concat 실패")
        print("stdout:")
        print(e.stdout)
        print("stderr:")
        print(e.stderr)
        raise

    return out_path

# --------------------------------------------------
# LLM: 포스터 기반 Veo 프롬프트 생성
# --------------------------------------------------

MASCOT_VIDEO_SYSTEM_PROMPT = """
You are a professional festival MASCOT promo-video prompt designer for Google Veo 3.

## Role

Your job is to look at:
- one FESTIVAL MASCOT IMAGE, and
- FESTIVAL METADATA as JSON (name, period, location, concept, and a list of program_name items),

and then generate TWO English prompts for a Veo-based video workflow:

- `segment_1_mascot_prompt`: 0–8 seconds, energetic mascot intro + first activities
- `segment_2_mascot_prompt`: 8–15 seconds, remaining activities + final call-to-action

These two prompts will be used sequentially with Veo's image-to-video
and video-extension features, so motion, pacing, and camera movement
must connect smoothly between segment 1 and segment 2.

---

## How to use the metadata and programs

1. Read the festival metadata JSON carefully.
   - Understand the mood of the festival (family-friendly Christmas, winter night, etc.).
   - Understand the location and concept (village, park, forest, light festival, etc.).

2. Look at the program_name list and:
   - Interpret each item into a simple English idea (e.g., family craft booth, kids event,
     nighttime photo zone, themed playground).
   - Choose about FOUR (4) programs that are:
     - visually dynamic,
     - easy to understand without text,
     - strongly representative of the festival.

3. Across both segments:
   - The mascot must clearly experience these ~4 programs in sequence.
   - Each chosen program should feel like its own short scene
     (different corner of the festival, new activity, new props or environment details).

---

## Absolute rules

1. This is a **festival promotional mascot video**.
   - The mascot is always the main character.
   - The video’s goal is to make viewers want to join the festival
     by watching the mascot enjoy real activities.

2. Visual consistency:
   - The mascot design (colors, costume, proportions, material) must stay consistent
     with the mascot image.
   - Environments and props must match the winter / Christmas / night-village feeling
     when appropriate, or what is implied by the festival metadata.

3. On-screen text rules (VERY IMPORTANT):
   - NEVER show any on-screen text, titles, subtitles, or signs.
   - No Korean, no English, no letters at all.
   - The story and call-to-action must be expressed ONLY through visuals and mascot actions.

4. Pacing and camera:
   - Overall pacing must be **fast and energetic**, not slow:
     - quick but readable camera moves,
     - clear scene transitions between different programs,
     - no long static holds.
   - You MUST describe camera behavior explicitly, for example:
     - fast tracking shot following the mascot as it runs,
     - handheld-style camera for lively feeling,
     - quick orbit shot around the mascot during a key moment,
     - whip-pan or fast cut to move between one program area and the next.
   - Energy should build as the video progresses, but it must not become chaotic or confusing.

---

## Timing & structure requirements

You MUST structure each prompt with time labels and bullet points,
and you MUST map the selected programs onto specific time ranges.

### 1) `segment_1_mascot_prompt` (0–8 seconds)

The text MUST start with:

`Generate an 8-second high-energy mascot teaser from this festival mascot image and metadata.`

Then define sub-phases with time labels and bullet points, for example:

`0–2s (Mascot Hero Intro):`
- Start with a dynamic close-up shot of the mascot in a snowy Christmas village environment
  that matches the original image style.
- The camera performs a quick, energetic move (e.g., dolly-in + slight handheld wobble)
  as the mascot reacts happily to the start of the festival
  (e.g., big smile, excited wave, hugging a glowing gift).

`2–8s (First Programs Highlight):`
- Quickly transition through about TWO selected festival programs.
- For each chosen program:
  - Move the mascot to a new corner of the festival that visually represents that program
    (e.g., interactive kids event zone, family activity booth, winter playground, light tunnel).
  - Describe clearly what the mascot is physically doing in that activity
    (e.g., sliding, crafting, playing, posing for photos).
  - Use explicit, high-energy camera descriptions:
    - tracking beside the mascot as it moves,
    - low-angle shot to amplify excitement,
    - fast but smooth whip-pan between program areas.
- Ensure each mini-scene is short, punchy, and easy to read,
  with no on-screen text at any time.

### 2) `segment_2_mascot_prompt` (8–15 seconds)

The text MUST start with:

`Extend the mascot teaser to 15 seconds.`

Then define sub-phases with time labels and bullet points, for example:

`8–13s (More Programs, Energy Builds):`
- Continue with the remaining selected programs so that, across segments 1 and 2,
  the mascot has clearly experienced about four different activities in total.
- For each remaining program:
  - Place the mascot into a visually distinct scene
    (e.g., nighttime photo zone with sparkling lights, family event stage, special show area).
  - Show a clear, fun action in that activity
    (e.g., posing with visitors, jumping with joy under lights, playing a simple game).
  - Use dynamic camera moves:
    - fast tracking around the mascot,
    - short orbit shots,
    - quick cuts or whip-pans between activities to keep strong tempo.
- Let the overall rhythm feel like a highlight reel of the festival,
  driven by the mascot’s movement and reactions.

`13–15s (Mascot Call-to-Action Finale):`
- Move into a final hero shot of the mascot in the most iconic area of the festival.
- The camera settles into a strong, stable composition while still feeling cinematic
  (e.g., slow dolly-in or slight orbit as the motion eases).
- The mascot performs a clear, enthusiastic call-to-action only through body language, such as:
  - waving both arms to invite the viewer,
  - pointing toward the festival behind them and then toward the viewer,
  - jumping and landing in an open, welcoming pose.
- Final 0.5 seconds:
  - all movement slows and stabilizes on the mascot’s inviting pose,
  - snow and background motion become subtle and calm,
  - absolutely no on-screen text or additional effects appear after this moment.

---

## Output format (VERY IMPORTANT)

You must return ONLY JSON of the following form:

{
  "segment_1_mascot_prompt": "<full English prompt for the first 0–8 seconds, following the structure above>",
  "segment_2_mascot_prompt": "<full English prompt for 8–15 seconds, following the structure above>"
}

- Do NOT include Korean in any field.
- Do NOT include any on-screen text instructions inside the prompts.
- Do NOT wrap the JSON in backticks or markdown fences.
"""



def _encode_image_to_small_data_url(image_path: str, max_size: int = 256, quality: int = 60) -> str:
    """
    포스터 이미지를 Vision용으로만 쓸 작은 썸네일로 줄여서
    data:image/jpeg;base64,... 형태로 변환 (TPM 방지용).
    """
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"포스터 파일을 찾을 수 없음: {image_path}")

    img = Image.open(p).convert("RGB")
    img.thumbnail((max_size, max_size), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def generate_mascot_video_prompts(
    image_path: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
    concept_description: str,
    program_name: Optional[List[str]] = None,
) -> Dict[str, str]:
    """
    포스터 + 메타데이터 기반으로 Veo용 segment_1, segment_2 프롬프트 생성
    """
    print("🚀 마스코트 영상 프롬프트 생성 시작")
    
    program_name = program_name or []  # None 방어
    programs_block = "\n".join(f"- {name}" for name in program_name)
    mascot_data_url = _encode_image_to_small_data_url(image_path)

    meta_json = json.dumps(
        {
            "festival_name_ko": festival_name_ko,
            "festival_period_ko": festival_period_ko,
            "festival_location_ko": festival_location_ko,
            "concept_description": concept_description,
            "program_name" : program_name
        },
        ensure_ascii=False,
    )

    user_text = (
        "You will receive FESTIVAL METADATA (in JSON) and a POSTER IMAGE.\n"
        "Use both to design segment_1_prompt and segment_2_prompt as Veo-ready prompts.\n\n"
        "Do NOT include Korean in any field.\n\n"
        "Festival metadata JSON:\n"
        f"{meta_json}\n\n"
        "Program list:\n"
        f"{programs_block}\n"
    )

    resp = openai_client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": MASCOT_VIDEO_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": mascot_data_url}},
                ],
            },
        ],
    )

    data = json.loads(resp.choices[0].message.content)
    return data


# --------------------------------------------------
# URL/상대경로 → 실제 파일 경로 변환
# --------------------------------------------------

def _resolve_mascot_path_from_url(mascot_image_url: str, project_id: str | int) -> Path:
    """
    mascot_image_url 이
    - http 로 시작하면: 다운로드해서 임시 파일로 사용
    - / 로 시작하거나 data/... 형태면: FRONT_PROJECT_ROOT/public 기준 상대경로로 사용
    """
    # http(s) URL 인 경우 → 임시 다운로드
    if mascot_image_url.startswith("http://") or mascot_image_url.startswith("https://"):
        tmp_dir = Path("generated_videos")
        tmp_dir.mkdir(exist_ok=True)
        tmp_path = tmp_dir / f"mascot_input_{project_id}.png"

        print(f"🌐 원격 포스터 이미지 다운로드: {mascot_image_url}")
        resp = requests.get(mascot_image_url, stream=True)
        resp.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return tmp_path

    # 이미 절대 경로인 파일이면 그대로 쓴다 (public 뒤에 다시 붙이면 경로가 두 번 겹친다)

    as_is = Path(mascot_image_url)

    if as_is.is_absolute() and as_is.exists():

        return as_is


    # 로컬 경로 (프론트 public 기준 상대경로라고 가정)
    front_root = Path(FRONT_PROJECT_ROOT)
    public_root = front_root / "public"

    # mascot_image_url 이 "/data/..." 이거나 "data/..." 인 케이스
    rel = mascot_image_url.lstrip("/")  # 맨 앞 / 제거
    mascot_path = public_root / rel
    return mascot_path


# --------------------------------------------------
# 메인 엔트리: run_poster_video_to_editor
# --------------------------------------------------

def run_mascot_video_to_editor(
    *,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
    project_id: int | str,
    mascot_image_url: str,
    concept_description: str,
    program_name=list[str]
) -> Dict[str, Any]:
    """
    우리가 약속한 입력만 받는 엔트리 함수.

    파이프라인:
    1) mascot_image_url → 실제 포스터 이미지 파일 경로 계산
    2) LLM으로 Veo 프롬프트 2개 생성
    3) Veo로 8초 + 확장 7초 영상 생성
    4) FFmpeg으로 15초 합치기
    5) FRONT_PROJECT_ROOT/public/data/promotion/M000001/{project_id}/video/poster_video.mp4 저장
    6) DB 저장용 dict 4개 필드 반환
    """
    pNo = str(project_id)

    # 1. 포스터 이미지 실제 경로
    start_image_path = _resolve_mascot_path_from_url(mascot_image_url, pNo)
    if not start_image_path.exists():
        raise FileNotFoundError(f"포스터 이미지가 존재하지 않습니다: {start_image_path}")

    # 2. LLM 프롬프트 생성
    prompts = generate_mascot_video_prompts(
        image_path=str(start_image_path),
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
        concept_description=concept_description,
        program_name=program_name,
    )

    segment_1 = prompts.get("segment_1_mascot_prompt", "")
    segment_2 = prompts.get("segment_2_mascot_prompt", "")

    if not segment_1 or not segment_2:
        raise ValueError("LLM이 segment_1_prompt 또는 segment_2_prompt를 생성하지 못했습니다.")

    segment_paths: list[Path] = []

    # 3. 첫 8초 이미지→비디오
    video_1, path_1 = generate_image_to_video(
        prompt=segment_1,
        start_image_path=str(start_image_path),
        end_image_path=None,
        download_name=f"mascot_segment_1_{pNo}_8s.mp4",
    )
    if path_1:
        segment_paths.append(path_1)

    # 4. 확장 7초
    video_2, path_2 = (None, None)
    if video_1:
        video_2, path_2 = extend_video(
            existing_video=video_1,
            extension_prompt=segment_2,
            duration_s=7,
            download_name=f"mascot_segment_2_{pNo}_7s.mp4",
        )
        if path_2:
            segment_paths.append(path_2)

        # NOTE:
    # - 예전에는 segment_1(8s) + segment_2(7s)를 우리가 FFmpeg로 이어붙였지만,
    #   지금은 Veo가 두 번째 결과를 이미 "완성본"으로 준다고 가정.
    # - 따라서 segment_2 결과(path_2)를 본편으로 사용하고,
    #   그 앞에 2초 인트로(검정 배경 + 축제명/기간)를 붙인다.

    if not path_2:
        raise RuntimeError("Veo 확장 비디오(segment_2)가 생성되지 않았습니다.")

    main_video_path = path_2  # ← Veo 두 번째 결과를 최종 본편으로 사용

    # 5. 인트로(검정 배경 + 축제명/기간) 2초 생성 → 본편과 concat

    # 5-1) 본편 해상도 추출
    width, height = get_video_resolution(str(main_video_path))
    print(f"🎞 본편 해상도: {width} x {height}")

    # 5-2) 인트로 영상 생성 (generated_videos 폴더 하위)
    DOWNLOAD_DIR = Path("generated_videos")
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    intro_output = DOWNLOAD_DIR / f"mascot_intro_{pNo}_2s.mp4"
    intro_video_path = create_black_intro_with_text(
        output_video=str(intro_output),
        width=width,
        height=height,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        font_path=str(INTRO_FONT_PATH),
        duration=2.0,
        fps=30,
    )

    # 5-3) 인트로 + 본편 concat (임시 최종본)
    final_temp = concat_intro_and_main(
        intro_video=str(intro_video_path),
        main_video=str(main_video_path),
        output_video=str(DOWNLOAD_DIR / f"mascot_video_{pNo}_with_intro.mp4"),
    )

    # 6. FRONT public/data/promotion/M000001/{pNo}/video/poster_video.mp4 로 이동
    front_root = Path(FRONT_PROJECT_ROOT)
    public_root = front_root / "public"
    rel_dir = Path("data") / "promotion" / PROMOTION_CODE / pNo / "video"
    target_dir = public_root / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / "mascot_video.mp4"
    shutil.move(str(final_temp), target_path)
    print(f"✅ 최종 포스터 홍보 영상 저장: {target_path}")

    db_rel_path = (Path("data") / "promotion" / PROMOTION_CODE / pNo / "video" / "mascot_video.mp4").as_posix()

    result: Dict[str, Any] = {
        "db_file_type": "mascot_video",
        "type": "video",
        "db_file_path": db_rel_path,
        "type_ko": "마스코트 홍보 영상",
    }
    print(result)

    return result



if __name__ == "__main__":
    """
    그냥 python make_poster_video.py 로 실행했을 때

    - FRONT_PROJECT_ROOT/public/data/promotion/M000001/10/poster/poster_1764222831_0.png
      이 포스터를 기반으로
    - Veo 3.1로 15초 포스터 홍보 영상 생성 후
    - FRONT_PROJECT_ROOT/public/data/promotion/M000001/10/video/poster_video.mp4 로 저장하고
    - DB에 넣을 dict 4개 필드를 출력한다.
    """

    # 프론트 public 기준 상대 경로 (절대경로 X)
    test_mascot_image_url = "data/promotion/M000001/10/poster/damdam.png"

    try:
        result = run_mascot_video_to_editor(
            festival_name_ko="제7회 담양 산타 축제",
            festival_period_ko="2025.12.23 ~ 2025.12.24",
            festival_location_ko="담양 메타랜드 일원",
            project_id=10,  # pNo = 10
            mascot_image_url=test_mascot_image_url,
            concept_description="겨울 담양 지역의 아름다운 겨울 풍경과 크리스마스 분위기를 보여주는 축제로, 방문객들에게 참여형, 관람객 주도형 경험을 제공. 지역 문화예술을 활용하여 상권 활성화와 다채로운 프로그램으로 오감 만족 경험을 선사.",
            program_name= ["크리스마스 테마의 다양한 체험 프로그램", "어린이 및 가족 대상 체험 및 이벤트", "야간경관 및 포토존 조성"]
        )

        print("\n✅ 파이프라인 실행 완료")
        print("결과 반환값 (DB 저장용 메타데이터):")
        print(result)

    except Exception as e:
        print("\n❌ 테스트 실행 중 오류 발생:")
        print(repr(e))