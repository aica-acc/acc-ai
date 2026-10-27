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
from app.core import request_member  # 회원 폴더는 요청마다 (request_member)

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



def generate_text_to_video(
    prompt: str,
    end_image_path: str = None,
    download_name: str = "text_to_video.mp4",
) -> Tuple[Optional[Any], Optional[Path]]:
    """
    Veo 3.1을 사용하여 이미지 기반 비디오를 생성하고 다운로드합니다.
    """
    print(f"\n--- 1. text to Video 시작 (프롬프트: {prompt[:60]}...) ---")

    config_params = {}

    video_config = types.GenerateVideosConfig(**config_params) if config_params else None

    operation = veo_client.models.generate_videos(
        model=VEO_MODEL,
        prompt=prompt,
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

ETC_VIDEO_SYSTEM_PROMPT = """
You are a professional festival promo-video prompt designer for Google Veo 3,
creating a **realistic live-action festival highlight video** (text-to-video).

You will ONLY receive:
- FESTIVAL METADATA as JSON (name, period, location, concept, program_name list)

There is **NO poster image** in this workflow.

---

## Your thinking process (RESEARCH FIRST)

1. Carefully read the festival metadata:
   - Name, period (season, time of year),
   - Location (city, region, environment),
   - Concept / description (target audience, mood),
   - Program list (experience programs, events, night view, photo zones, etc.).

2. Before writing any prompt:
   - Internally infer what kind of real festival this would be in the real world.
   - Decide:
     - Daytime / night / mixed,
     - Crowd density,
     - Types of booths, food, lights, performances, family zones,
     - Weather (snow, autumn breeze, spring flowers, summer night air, etc.).

3. Use this “mental research” to design **plausible, grounded scenes** that feel like a real Korean local festival,
   not a random generic event.

---

## Absolute rules

1. This is a **festival promotional video**.
   - The video must clearly feel like a highlight trailer that invites people to visit the festival.
   - The energy should be fast, exciting, and welcoming.
   - Show diverse experiences: programs, food, night lights, photo zones, families, kids, young adults.

2. **NO ON-SCREEN TEXT AT ANY TIME.**
   - Absolutely no visible text, logos, banners, subtitles, signs, UI overlays, or titles.
   - The call-to-action must be conveyed only through:
     - camera motion,
     - character actions and gestures,
     - composition (e.g., walking toward entrance, people flowing into the festival).

3. Scene and pacing:
   - Use **at least 5 distinct scenes / cuts** across the 15 seconds.
   - Scene lengths should be fast and snappy (around 0.7–2.0 seconds each).
   - Include a mix of:
     - experience programs (rides, crafts, performances),
     - night view & photo zones,
     - food and drink,
     - crowd atmosphere that matches the concept.

4. Visual style:
   - The style must be realistic live-action, like footage shot on a cinema camera or gimbal or drone.
   - No cartoon, no anime, no 2D illustration look.
   - Lighting, color, and wardrobe should naturally match:
     - the season,
     - the climate,
     - the festival concept (e.g., winter Christmas, spring flower, mud, lanterns).

5. Camera behavior:
   - Use professional camera language:
     - gimbal walk-through shots,
     - handheld but stable close-ups,
     - drone establishing shots,
     - smooth whip-pans between scenes.
   - The camera should feel like a real human or drone operator moving through the festival.
   - No extreme glitch, no chaotic shakiness.

---

## Timing & structure requirements

You MUST format the prompts in this exact structure and timing.

### 1) `segment_1_etc_prompt` (0–8 seconds)

The text MUST start with exactly:

`Generate an 8-second realistic live-action festival highlight teaser.`

Then define sub-phases with time labels and bullet points:

`0–2s (Opening Establishing Shot):`
- A wide establishing shot that clearly shows the festival’s location and season
  (for example: winter night lights in a riverside park, bamboo forest with Christmas decorations, etc.).
- Describe where the camera is (drone, high angle, eye level) and how it moves.
- Show crowds arriving or moving, but keep faces soft / non-specific.

`2–6s (Fast Experience Montage – first 2–3 scenes):`
- Design a sequence of **2–3 rapid cuts** that show different experience activities.
- Use concrete things inferred from the program list and metadata:
  - e.g., kids doing hands-on crafts, families at a themed activity zone,
  - people laughing in a small performance zone, photo-taking behavior, etc.
- For each cut, specify:
  - camera position and motion,
  - what the people are doing,
  - how the lights and environment look.

`6–8s (Transition into Night Highlight Zone):`
- Move the camera toward the most visually impressive area (e.g., night view, photo zone, light tunnel).
- The last moment of segment 1 should end in a composition that can smoothly continue in segment 2.

---

### 2) `segment_2_etc_prompt` (8–15 seconds)

The text MUST start with exactly:

`Extend teaser to 15 seconds as a seamless continuation.`

Then define sub-phases:

`8–13s (More Experiences & Energy Build – additional 2–3 scenes):`
- Continue from the last frame of segment 1 with perfect continuity.
- Show **at least 2 more distinct experiences**, different from segment 1:
  - e.g., food stalls, local street food being served,
  - people warming their hands with hot drinks,
  - couples or families posing under light installations or in front of a landmark,
  - small live performance or parade moment if appropriate.
- Keep the camera movement energetic but controlled.
- Make sure every shot still feels like one coherent festival (same location, same season).

`13–15s (Final Call-to-Action Without Text):`
- Design a final hero shot that feels like a clear invitation to join the festival,
  but ONLY through visuals and body language.
  Examples:
  - Camera dollies toward the festival entrance as groups walk in.
  - A family or group of friends turns toward the camera, smiling and gesturing “come with us”.
  - The camera floats backward through the light tunnel while people walk toward the center.
- The last 0.5 seconds:
  - camera motion gently eases to a stop,
  - lights and people still move slightly,
  - no extra cuts or sudden moves.

---

## Output format (VERY IMPORTANT)

You must return ONLY JSON of the following form:

{
  "segment_1_etc_prompt": "<full English prompt for the first 0–8 seconds, following the structure above>",
  "segment_2_etc_prompt": "<full English prompt for 8–15 seconds, following the structure above>"
}

- Do NOT include Korean in any field.
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


def generate_etc_video_prompts(
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
    concept_description: str,
    program_name: Optional[List[str]] = None,
) -> Dict[str, str]:
    """
    포스터 + 메타데이터 기반으로 Veo용 segment_1, segment_2 프롬프트 생성
    """
    print("🚀 기타 홍보 영상 프롬프트 생성 시작")
    
    program_name = program_name or []  # None 방어
    programs_block = "\n".join(f"- {name}" for name in program_name)

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
            {"role": "system", "content": ETC_VIDEO_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                ],
            },
        ],
    )

    data = json.loads(resp.choices[0].message.content)
    return data


# --------------------------------------------------
# URL/상대경로 → 실제 파일 경로 변환
# --------------------------------------------------

# --------------------------------------------------
# 메인 엔트리: run_poster_video_to_editor
# --------------------------------------------------

def run_etc_video_to_editor(
    *,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
    project_id: int | str,
    concept_description: str,
    program_name=list[str]
) -> Dict[str, Any]:
    """
    우리가 약속한 입력만 받는 엔트리 함수.

    파이프라인:
    2) LLM으로 Veo 프롬프트 2개 생성
    3) Veo로 8초 + 확장 7초 영상 생성
    4) FFmpeg으로 15초 합치기
    5) FRONT_PROJECT_ROOT/public/data/promotion/M000001/{project_id}/video/etc_video.mp4 저장
    6) DB 저장용 dict 4개 필드 반환
    """
    pNo = str(project_id)

    # 1. 포스터 이미지 실제 경로

    # 2. LLM 프롬프트 생성
    prompts = generate_etc_video_prompts(
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
        concept_description=concept_description,
        program_name=program_name,
    )

    segment_1 = prompts.get("segment_1_etc_prompt", "")
    segment_2 = prompts.get("segment_2_etc_prompt", "")

    if not segment_1 or not segment_2:
        raise ValueError("LLM이 segment_1_prompt 또는 segment_2_prompt를 생성하지 못했습니다.")

    segment_paths: list[Path] = []

    # 3. 첫 8초 이미지→비디오
    video_1, path_1 = generate_text_to_video(
        prompt=segment_1,
        end_image_path=None,
        download_name=f"segment_1_etc_prompt_{pNo}_8s.mp4",
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
            download_name=f"segment_2_etc_prompt_{pNo}_7s.mp4",
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

    intro_output = DOWNLOAD_DIR / f"etc_intro_{pNo}_2s.mp4"
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
        output_video=str(DOWNLOAD_DIR / f"etc_video_{pNo}_with_intro.mp4"),
    )

    # 6. FRONT public/data/promotion/M000001/{pNo}/video/poster_video.mp4 로 이동
    front_root = Path(FRONT_PROJECT_ROOT)
    public_root = front_root / "public"
    rel_dir = Path("data") / "promotion" / request_member.member_no() / pNo / "video"
    target_dir = public_root / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / "etc_video.mp4"
    shutil.move(str(final_temp), target_path)
    print(f"✅ 최종 포스터 홍보 영상 저장: {target_path}")

    db_rel_path = (Path("data") / "promotion" / request_member.member_no() / pNo / "video" / "etc_video.mp4").as_posix()

    result: Dict[str, Any] = {
        "db_file_type": "etc_video",
        "type": "video",
        "db_file_path": db_rel_path,
        "type_ko": "기타 홍보 영상",
    }

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

    try:
        result = run_etc_video_to_editor(
            festival_name_ko="제7회 담양 산타 축제",
            festival_period_ko="2025.12.23 ~ 2025.12.24",
            festival_location_ko="담양 메타랜드 일원",
            project_id=10,  # pNo = 10
            concept_description="겨울 담양 지역의 아름다운 겨울 풍경과 크리스마스 분위기를 보여주는 축제로, 방문객들에게 참여형, 관람객 주도형 경험을 제공. 지역 문화예술을 활용하여 상권 활성화와 다채로운 프로그램으로 오감 만족 경험을 선사.",
            program_name= ["크리스마스 테마의 다양한 체험 프로그램", "어린이 및 가족 대상 체험 및 이벤트", "야간경관 및 포토존 조성"]
        )

        print("\n✅ 파이프라인 실행 완료")
        print("결과 반환값 (DB 저장용 메타데이터):")
        print(result)

    except Exception as e:
        print("\n❌ 테스트 실행 중 오류 발생:")
        print(repr(e))