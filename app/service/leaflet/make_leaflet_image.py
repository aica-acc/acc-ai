# app/service/leaflet/make_leaflet_replicate.py

import os
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, List

from dotenv import load_dotenv
from openai import OpenAI
import replicate
import requests

load_dotenv()

# --------------------------------------------------
# 공통 설정
# --------------------------------------------------
PROJECT_ROOT = os.getenv("PROJECT_ROOT")
FRONT_PROJECT_ROOT = os.getenv("FRONT_PROJECT_ROOT")
PROMOTION_CODE = "M000001"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not PROJECT_ROOT or not FRONT_PROJECT_ROOT:
    raise ValueError("PROJECT_ROOT, FRONT_PROJECT_ROOT 가 .env에 설정되어 있지 않습니다.")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY 가 .env에 설정되어 있지 않습니다.")
if not REPLICATE_API_TOKEN:
    raise ValueError("REPLICATE_API_TOKEN 이 .env에 설정되어 있지 않습니다.")

PROJECT_ROOT = Path(PROJECT_ROOT).resolve()
openai_client = OpenAI()   # OPENAI_API_KEY 는 환경변수로 자동 인식됨


# --------------------------------------------------
# LLM 시스템 프롬프트: 한글 텍스트까지 포함된 4컷 리플렛
# --------------------------------------------------

LEAFLET_SYSTEM_PROMPT = """
You are a professional festival leaflet prompt designer.

## Goal

Your job is to use:
- IMAGE 1: a FESTIVAL POSTER style reference,
- IMAGE 2: a LEAFLET LAYOUT reference,
- and FESTIVAL METADATA in JSON (Korean name, period, location, concept, program list),

to generate ONE detailed English prompt for the model
`google/nano-banana-pro` on Replicate that will:

- keep the illustration STYLE and color feeling of IMAGE 1,
- adopt the overall multi-column LAYOUT structure of IMAGE 2,
- and render a fully finished leaflet image with real, readable Korean text
  for the festival title, period, location, and program information.

This leaflet will be used as-is. There will be NO manual text editing afterwards,
so the Korean text must be sharp, accurate, and clearly legible.

---

## How to use the two reference images

1. Reference images
   - The image model receives TWO separate reference images:
     - First reference image (index 0): festival poster style reference (Image 1).
     - Second reference image (index 1): leaflet layout reference (Image 2).
   - In your prompt, you MUST explicitly describe them as:
     - "the first reference image" = style and mood reference,
     - "the second reference image" = layout and four-panel structure reference.
   - The generated leaflet should be a new single 16:9 canvas, not a collage.

2. Layout requirements (four-panel leaflet)
   - The leaflet MUST be designed as four vertical panels inside a 16:9 canvas.
   - Each panel has equal width and the same height.
   - Use thin but clear vertical separators between panels.
   - Assign roles:
     - Panel 1 (left): main hero visual + big Korean festival title and a short concept line.
     - Panel 2: key programs list in Korean.
     - Panel 3: schedule / timetable in Korean.
     - Panel 4 (right): venue, location, transportation info in Korean,
       plus small icons or a simplified map.

3. Use of festival metadata (Korean text)
   - You MUST use the Korean strings from the JSON exactly as they are:
     - `festival_name_ko` for the main title (large Korean text).
     - `festival_period_ko` near the title or in the schedule area.
     - `festival_location_ko` in the map/info panel.
   - For the `program_name` list:
     - Choose about 3–5 items and render them as bullet-like lines in Korean
       in the programs panel.
   - Do NOT translate Korean into English.
   - Do NOT invent fake program names or change the given Korean phrases.

---

## Text rendering rules (VERY IMPORTANT)

- The generated image must contain clear, readable Korean text.
- The main title must show `festival_name_ko` exactly, with correct spacing.
- Period and location must show `festival_period_ko` and `festival_location_ko` exactly.
- Program list should contain the original Korean program names as short lines.
- An additional small English subtitle for the festival name is OPTIONAL:
  - If used, place it below or above the Korean title in a smaller font.

- Fonts:
  - Ask the model for clean, modern, festive fonts that handle Korean nicely
    (no deformed or broken glyphs).
  - Use high contrast between text and background
    (for example, dark navy background with bright white or gold text).

- Do NOT let characters or decorations overlap the important text.
- Do NOT fill tables or map areas with overwhelming text; keep them readable and organized.

---

## Visual & technical requirements

- Aspect ratio: exactly 16:9, horizontal leaflet.
- Four vertical panels with clear separators.
- Style: follow the illustration style and color palette of the poster (first reference image).
- Layout: follow the structure of the leaflet reference (second reference image),
  but do not copy it exactly one-to-one.
- Make the overall design feel festive, winter/Christmas themed,
  and suitable for a real printed leaflet.

---

## Output

You must return ONLY JSON of the following form:

{
  "leaflet_prompt": "<full detailed English prompt for google/nano-banana-pro on Replicate>"
}

- Do NOT include Korean in the JSON keys.
- The `leaflet_prompt` must explicitly mention:
  - that the first reference image is for style,
  - that the second reference image is for layout,
  - that the layout uses four vertical panels with specific roles,
  - that the model must render real Korean text using the given strings
    for title, period, location, and program names.
- Do NOT wrap the JSON in backticks or markdown.
"""


# --------------------------------------------------
# URL/상대경로 → 실제 파일 경로 변환
# --------------------------------------------------

def _resolve_front_asset(path_or_url: str, project_id: str | int) -> Path:
    """
    - http(s) 이면 다운로드해서 임시 파일로 사용
    - 아니면 FRONT_PROJECT_ROOT/public 기준 상대경로로 사용
    """
    # http(s) → 임시 다운로드
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        tmp_dir = Path("generated_leaflet_refs")
        tmp_dir.mkdir(exist_ok=True)
        tmp_path = tmp_dir / f"leaflet_ref_{project_id}.png"

        print(f"🌐 원격 이미지 다운로드: {path_or_url}")
        resp = requests.get(path_or_url, stream=True)
        resp.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return tmp_path

    # 로컬 (FRONT public 기준)
    front_root = Path(FRONT_PROJECT_ROOT)
    public_root = front_root / "public"
    rel = path_or_url.lstrip("/")
    return public_root / rel


# --------------------------------------------------
# 1단계: LLM으로 Nano Banana용 프롬프트 생성
# --------------------------------------------------

def generate_leaflet_prompt_from_metadata(
    *,
    poster_style_path: Path,
    layout_ref_path: Path,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
    concept_description: str,
    program_name: Optional[List[str]] = None,
) -> str:
    """
    메타데이터 기반으로, Nano Banana Pro에 넣을 detailed prompt 한 줄 생성.
    (이미지 자체는 LLM에 안 넣고, 두 이미지의 역할을 텍스트로 설명하는 방식)
    """
    program_name = program_name or []

    meta_json = json.dumps(
        {
            "festival_name_ko": festival_name_ko,
            "festival_period_ko": festival_period_ko,
            "festival_location_ko": festival_location_ko,
            "concept_description": concept_description,
            "program_name": program_name,
        },
        ensure_ascii=False,
    )

    programs_block = "\n".join(f"- {p}" for p in program_name)

    user_text = (
        "You will design a single detailed prompt for google/nano-banana-pro on Replicate.\n"
        "The image model will receive TWO reference images in the `image_input` array:\n"
        "- index 0 (first reference image): the festival poster style reference (Image 1).\n"
        "- index 1 (second reference image): the leaflet layout reference (Image 2).\n\n"
        "Use the first reference image for overall illustration style, colors, and mood.\n"
        "Use the second reference image for the four-panel leaflet layout structure.\n\n"
        "The final leaflet must be a finished 16:9 horizontal design with four vertical panels,\n"
        "and it MUST include real, readable Korean text for:\n"
        "- the festival title (festival_name_ko),\n"
        "- the period (festival_period_ko),\n"
        "- the location (festival_location_ko),\n"
        "- and a short list of main programs from program_name.\n"
        "Do not translate the Korean strings. Use them exactly as they appear in the metadata.\n\n"
        "Festival metadata JSON:\n"
        f"{meta_json}\n\n"
        "Program list:\n"
        f"{programs_block}\n"
    )

    resp = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": LEAFLET_SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    )

    data = json.loads(resp.choices[0].message.content)
    leaflet_prompt: str = data.get("leaflet_prompt", "")
    if not leaflet_prompt:
        raise ValueError("LLM이 leaflet_prompt 를 생성하지 못했습니다.")
    print("🧠 LLM leaflet_prompt 생성 완료.")
    return leaflet_prompt


# --------------------------------------------------
# 2단계: Replicate + google/nano-banana-pro 호출
# --------------------------------------------------

def generate_leaflet_with_replicate(
    *,
    leaflet_prompt: str,
    poster_path: Path,
    layout_path: Path,
    download_name: str = "leaflet_nano_banana.png",
) -> Path:
    """
    Replicate 의 google/nano-banana-pro 모델을 호출해서
    포스터 + 레이아웃 두 장을 참조 이미지로 써서 리플렛 이미지를 생성한다.
    """
    from pathlib import Path as _Path

    print("\n--- Nano Banana Pro (Replicate) 리플렛 생성 시작 ---")
    print("모델: google/nano-banana-pro")
    print("요청 prompt 일부:", leaflet_prompt[:120], "...")

    output_dir = _Path("generated_leaflets_replicate")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / download_name

    with open(poster_path, "rb") as poster_file, open(layout_path, "rb") as layout_file:
        # google/nano-banana-pro 의 입력 스키마에 맞춰 image_input 배열에 두 장 넣기
        output = replicate.run(
            "google/nano-banana-pro",
            input={
                "prompt": leaflet_prompt,
                "image_input": [poster_file, layout_file],
                # 필요하면 여기서 aspect_ratio / resolution 등 옵션 추가
                # "aspect_ratio": "16:9",
                # "resolution": "2K",
            },
        )

    # 이 모델은 FileOutput 하나를 반환한다고 가정 (리스트 아님)
    with open(output_path, "wb") as f:
        f.write(output.read())

    print(f"🖼  리플렛 이미지 다운로드 완료: {output_path.resolve()}")
    return output_path


# --------------------------------------------------
# 3단계: ACC 파이프라인 엔트리
# --------------------------------------------------

def run_leaflet_to_editor(
    *,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
    project_id: int | str,
    poster_image_url: str,         # 스타일 참고용 포스터
    layout_ref_image_url: str,     # 4컷 레이아웃 참고 이미지
    concept_description: str,
    program_name: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Replicate + Nano Banana Pro 로 '완성형 한글 리플렛' 생성.

    1) poster_image_url, layout_ref_image_url → 실제 파일 경로
    2) LLM 으로 Nano Banana Pro용 prompt 생성
    3) Replicate 호출 → 리플렛 이미지 생성
    4) FRONT_PROJECT_ROOT/public/data/promotion/M000001/{pNo}/image/leaflet_nano.png 저장
    5) DB 저장용 dict 반환
    """
    pNo = str(project_id)

    # 1. 참조 이미지 실제 경로
    poster_path = _resolve_front_asset(poster_image_url, pNo)
    layout_path = _resolve_front_asset(layout_ref_image_url, pNo)

    if not poster_path.exists():
        raise FileNotFoundError(f"포스터 이미지가 존재하지 않습니다: {poster_path}")
    if not layout_path.exists():
        raise FileNotFoundError(f"레이아웃 참고 이미지가 존재하지 않습니다: {layout_path}")

    # 2. LLM 프롬프트 생성
    leaflet_prompt = generate_leaflet_prompt_from_metadata(
        poster_style_path=poster_path,
        layout_ref_path=layout_path,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
        concept_description=concept_description,
        program_name=program_name,
    )

    # 3. Nano Banana Pro 호출
    nano_output_path = generate_leaflet_with_replicate(
        leaflet_prompt=leaflet_prompt,
        poster_path=poster_path,
        layout_path=layout_path,
        download_name=f"leaflet_nano_{pNo}.png",
    )

    # 4. FRONT public/data/... 로 이동
    front_root = Path(FRONT_PROJECT_ROOT)
    public_root = front_root / "public"
    rel_dir = Path("data") / "promotion" / PROMOTION_CODE / pNo / "image"
    target_dir = public_root / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / "leaflet_nano.png"
    shutil.move(str(nano_output_path), target_path)
    print(f"✅ 최종 리플렛 이미지 저장: {target_path}")

    db_rel_path = (
        Path("data") / "promotion" / PROMOTION_CODE / pNo / "image" / "leaflet_nano.png"
    ).as_posix()

    result: Dict[str, Any] = {
        "db_file_type": "leaflet_nano",
        "type": "image",
        "db_file_path": db_rel_path,
        "type_ko": "리플렛 이미지 (한글 텍스트 포함)",
    }
    return result


# --------------------------------------------------
# 단독 테스트용
# --------------------------------------------------

if __name__ == "__main__":
    """
    예시 실행:

    - 포스터: FRONT/public/data/promotion/M000001/25/poster/poster_1764735707_3.png
    - 레이아웃: FRONT/public/data/promotion/M000001/25/poster/good_2.png (예시)
    """

    test_poster_image_url = "data/promotion/M000001/25/poster/poster_1764735707_3.png"
    test_layout_ref_url = "data/promotion/M000001/25/poster/good_2.jpg"

    try:
        result = run_leaflet_to_editor(
            festival_name_ko="제7회 담양 산타 축제",
            festival_period_ko="2025.12.23 ~ 2025.12.24",
            festival_location_ko="담양 메타랜드 일원",
            project_id=25,
            poster_image_url=test_poster_image_url,
            layout_ref_image_url=test_layout_ref_url,
            concept_description="따뜻한 조명과 겨울 산타 마을 분위기를 살린 가족 참여형 크리스마스 축제",
            program_name=[
                "크리스마스 테마의 다양한 체험 프로그램",
                "어린이 및 가족 대상 체험 및 이벤트",
                "야간경관 및 포토존 조성",
            ],
        )

        print("\n✅ 파이프라인 실행 완료")
        print("결과 반환값 (DB 저장용 메타데이터):")
        print(result)
    except Exception as e:
        print("\n❌ 테스트 실행 중 오류 발생:")
        print(repr(e))
