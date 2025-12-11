# app/service/poster_cardnews/make_poster_cardnews_replicate.py

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

POSTER_CARDNEWS_SYSTEM_PROMPT = """
You are a professional festival poster_cardnews prompt designer.

## GOAL

Your job is to use:
- IMAGE 1: a FESTIVAL POSTER style reference,
- IMAGE 2: a POSTER_CARDNEWS / TRIFOLD layout reference,
- and FESTIVAL METADATA in JSON (Korean name, period, location, concept, program list),

to generate ONE detailed English prompt for the model
`google/nano-banana-pro` on Replicate that will:

- keep the illustration STYLE, atmosphere, and color feeling of IMAGE 1,
- adopt the overall multi-panel POSTER_CARDNEWS structure of IMAGE 2
  (like a real printed Korean festival brochure),
- and render a fully finished poster_cardnews image with **real, readable Korean text**
  for the festival title, period, location, programs, schedule, and basic guide info.

This poster_cardnews will be used as-is. There will be NO manual text editing afterwards,
so the Korean text must be sharp, accurate, and clearly legible.
The composition must feel like an actual local government festival poster_cardnews,
not like a simple poster collage.

---

## HOW TO USE THE TWO REFERENCE IMAGES

1. Reference images

   - The image model receives TWO separate reference images:
     - First reference image (index 0): festival poster style reference (Image 1).
     - Second reference image (index 1): poster_cardnews layout / trifold reference (Image 2).

   - In your prompt, you MUST explicitly describe:
     - "the first reference image" = style, color palette, overall festive mood.
     - "the second reference image" = layout, multi-panel brochure structure.

   - The generated poster_cardnews must be a **single 1:1 canvas**,
     NOT a collage of multiple separate images.

2. Overall layout: four-panel poster_cardnews in 1:1:

   - Design the poster_cardnews as **four vertical panels** inside a 1:1 horizontal canvas.
   - Each panel has equal width and the same height.
   - Use thin but clear vertical separators between panels,
     similar to a folded paper poster_cardnews.
   - Keep a small outer margin so it looks like a printed brochure,
     not edge-to-edge bleed.

3. Panel roles and detailed content

   **Panel 1 (left cover) – 메인 표지**

   - Large hero illustration following the style and mood of the first reference image.
   - Big Korean festival title using `festival_name_ko`.
   - Under the title, show the festival period using `festival_period_ko`.
   - Optionally add a very short English subtitle for the festival name.
   - Add one short Korean concept line summarizing the festival atmosphere,
     based on `concept_description`.

   **Panel 2 – 주요 프로그램 / 하이라이트 소개**

   - Section title like “주요 프로그램” in Korean.
   - Use `program_name` list as the core items.
   - You may expand each item with a short Korean description line.
   - You may add 1–3 additional realistic program items in Korean
     that match the festival concept (e.g. Santa parade, night view zone,
     photo zone, family experience, etc.).
   - Use bullet-style layout or small icons to make it look like a real poster_cardnews.

   **Panel 3 – 일정표 및 이벤트 안내**

   - Section title like “축제 일정표” or “프로그램 일정”.
   - Draw a clear Korean timetable-style table:
     - Left column: 날짜 또는 요일.
     - Middle/right columns: 시간대와 프로그램 이름.
   - It does not need to be historically accurate; you may create a realistic schedule
     based on `program_name` and the concept.
   - You may add a small boxed area for “이벤트 안내” or “할인 정보” in Korean,
     similar to the third sample poster_cardnews:
     - e.g. shuttle, discount for local shops, special night event, etc.

   **Panel 4 (right) – 장소 · 교통 · 안내 정보**

   - Section title like “장소 및 교통 안내” in Korean.
   - Show the location using `festival_location_ko` near the top.
   - Include a simplified illustrated map area:
     - Main festival zone, nearby landmarks, parking icons, shuttle icons.
   - Add bullet points for:
     - 셔틀버스 운행 안내 (times/route can be fictional but realistic).
     - 주차장 위치 및 간단 안내.
     - 연락처 또는 홈페이지 주소 (you may invent a plausible URL/phone number).
   - Use small, neat icons (bus, car, map pin) with short Korean labels.

---

## USE OF FESTIVAL METADATA (KOREAN TEXT)

You MUST use the Korean strings from the JSON:

- `festival_name_ko` → main title in Panel 1 (large Korean text).
- `festival_period_ko` → period text in Panel 1 or Panel 3.
- `festival_location_ko` → location text in Panel 4.

For `program_name`:

- Use them as the core program lines in Panel 2 and/or Panel 3.
- You MAY:
  - slightly rephrase or shorten them in Korean for better readability,
  - and you MAY add extra realistic program names in Korean
    that match the festival mood and concept.

Do NOT translate Korean into English.
Do NOT replace the festival name, period, or location with English.

---

## TEXT RENDERING RULES (VERY IMPORTANT)

- The generated image must contain **clear, readable Korean text**.
- The main title must show `festival_name_ko` exactly (correct spacing and spelling).
- Period and location must show `festival_period_ko` and `festival_location_ko` exactly.
- Program list, schedule table, and guide information must be written in natural Korean.
- English can appear only as small subtitles or secondary labels.

Fonts:

- Ask the model for clean, modern, festive fonts that support Korean properly
  (no broken or deformed glyphs).
- Use high contrast between text and background
  (e.g. deep navy night sky background with bright warm text colors).
- Use different font sizes and weights for hierarchy:
  - large bold for title,
  - medium for headings,
  - smaller regular for body text and tables.

Do NOT let characters or decorations overlap the important text.
Keep tables, map, and program sections **organized and readable**, not cluttered.

---

## VISUAL & TECHNICAL REQUIREMENTS

- Aspect ratio: exactly 1:1, horizontal.
- Four vertical panels with clear separators and small outer margins.
- Style: follow the illustration style and color palette of the first reference image
  (warm winter night, festive lights, family-friendly).
- Layout: follow the structure of the second reference image and
  typical Korean festival brochures (like a tourism office poster_cardnews),
  but do not copy any single reference exactly.
- The overall design must look like a professionally printed poster_cardnews:
  balanced typography, aligned columns, tables, and information blocks.

---

## OUTPUT FORMAT

You must return ONLY JSON of the following form:

{
  "poster_cardnews_prompt": "<full detailed English prompt for google/nano-banana-pro on Replicate>"
}

- Do NOT include Korean in the JSON keys.
- The `poster_cardnews_prompt` must explicitly mention:
  - that the first reference image is for style and festive mood,
  - that the second reference image is for multi-panel poster_cardnews layout,
  - that the layout uses four vertical panels with the specific roles above,
  - that the model must render **real Korean text** using the given strings
    for title, period, location, and program names,
    plus additional realistic Korean schedule and guide information.
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
        tmp_dir = Path("generated_poster_cardnews_refs")
        tmp_dir.mkdir(exist_ok=True)
        tmp_path = tmp_dir / f"poster_cardnews_ref_{project_id}.png"

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

def generate_poster_cardnews_prompt_from_metadata(
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
        "You will design a **single, very detailed prompt** for `google/nano-banana-pro` on Replicate.\n"
        "The image model will receive TWO reference images in the `image_input` array:\n"
        "- index 0 (first reference image): the festival poster style reference (Image 1).\n"
        "- index 1 (second reference image): the poster_cardnews / brochure layout reference (Image 2).\n\n"
        "The final output must look like a **real Korean festival poster_cardnews** printed by a local government,\n"
        "with four vertical panels inside a 1:1 canvas.\n\n"
        "In your prompt, clearly instruct the model to:\n"
        "- follow the illustration style, colors, and mood of the first reference image,\n"
        "- follow the multi-panel poster_cardnews layout structure of the second reference image,\n"
        "- organize information into 4 panels: cover, programs, schedule, and map/transport guide,\n"
        "- fill the poster_cardnews with natural, readable Korean text based on the metadata.\n\n"
        "The poster_cardnews must feel dense with information but still clean and well-organized,\n"
        "similar to an official tourism brochure, not like a simple poster.\n\n"
        "Festival metadata JSON:\n"
        f"{meta_json}\n\n"
        "Program list (raw Korean strings):\n"
        f"\"\"\"\n{programs_block}\n\"\"\"\n"
        "Use these Korean strings for the title, period, location, and core programs.\n"
        "You may add extra realistic Korean program and schedule details that match the concept.\n"
    )

    resp = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": POSTER_CARDNEWS_SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    )

    data = json.loads(resp.choices[0].message.content)
    poster_cardnews_prompt: str = data.get("poster_cardnews_prompt", "")
    if not poster_cardnews_prompt:
        raise ValueError("LLM이 poster_cardnews_prompt 를 생성하지 못했습니다.")
    print("🧠 LLM poster_cardnews_prompt 생성 완료.")
    return poster_cardnews_prompt


# --------------------------------------------------
# 2단계: Replicate + google/nano-banana-pro 호출
# --------------------------------------------------

def generate_poster_cardnews_with_replicate(
    *,
    poster_cardnews_prompt: str,
    poster_path: Path,
    layout_path: Path,
    download_name: str = "poster_cardnews_nano_banana.png",
) -> Path:
    """
    Replicate 의 google/nano-banana-pro 모델을 호출해서
    포스터 + 레이아웃 두 장을 참조 이미지로 써서 리플렛 이미지를 생성한다.
    """
    from pathlib import Path as _Path

    print("\n--- Nano Banana Pro (Replicate) 리플렛 생성 시작 ---")
    print("모델: google/nano-banana-pro")
    print("요청 prompt 일부:", poster_cardnews_prompt[:120], "...")

    output_dir = _Path("generated_poster_cardnewss_replicate")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / download_name

    with open(poster_path, "rb") as poster_file, open(layout_path, "rb") as layout_file:
        # google/nano-banana-pro 의 입력 스키마에 맞춰 image_input 배열에 두 장 넣기
        output = replicate.run(
            "google/nano-banana-pro",
            input={
                "prompt": poster_cardnews_prompt,
                "image_input": [poster_file, layout_file],
                # 필요하면 여기서 aspect_ratio / resolution 등 옵션 추가
                # "aspect_ratio": "1:1",
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

def run_poster_cardnews_to_editor(
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
    4) FRONT_PROJECT_ROOT/public/data/promotion/M000001/{pNo}/image/poster_cardnews_nano.png 저장
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
    poster_cardnews_prompt = generate_poster_cardnews_prompt_from_metadata(
        poster_style_path=poster_path,
        layout_ref_path=layout_path,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
        concept_description=concept_description,
        program_name=program_name,
    )

    # 3. Nano Banana Pro 호출
    nano_output_path = generate_poster_cardnews_with_replicate(
        poster_cardnews_prompt=poster_cardnews_prompt,
        poster_path=poster_path,
        layout_path=layout_path,
        download_name=f"poster_cardnews_{pNo}.png",
    )

    # 4. FRONT public/data/... 로 이동
    front_root = Path(FRONT_PROJECT_ROOT)
    public_root = front_root / "public"
    rel_dir = Path("data") / "promotion" / PROMOTION_CODE / pNo / "poster_cardnews"
    target_dir = public_root / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / "poster_cardnews_nano.png"
    shutil.move(str(nano_output_path), target_path)
    print(f"✅ 최종 리플렛 이미지 저장: {target_path}")

    db_rel_path = (
        Path("data") / "promotion" / PROMOTION_CODE / pNo / "poster_cardnews" / "poster_cardnews_nano.png"
    ).as_posix()

    result: Dict[str, Any] = {
        "db_file_type": "poster_cardnews",
        "type": "image",
        "db_file_path": db_rel_path,
        "type_ko": "카든뉴스",
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

    test_poster_image_url = "data/promotion/M000001/25/poster/poster_1764735670_2.png"
    test_layout_ref_url = "data/promotion/M000001/25/poster/card.png"

    try:
        result = run_poster_cardnews_to_editor(
            festival_name_ko="제7회 담양 산타 축제",
            festival_period_ko="2025.12.23 ~ 2025.12.24",
            festival_location_ko="담양 메타랜드 일원",
            project_id=24,
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
