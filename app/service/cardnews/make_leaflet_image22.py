# app/service/leaflet/make_leaflet_image.py

import os
import io
import json
import base64
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, List

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import OpenAI
from PIL import Image

load_dotenv()

# --------------------------------------------------
# 공통 설정
# --------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROJECT_ROOT = os.getenv("PROJECT_ROOT")
FRONT_PROJECT_ROOT = os.getenv("FRONT_PROJECT_ROOT")
PROMOTION_CODE = "M000001"  # 고정값

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY 가 .env에 설정되어 있지 않습니다.")

if not PROJECT_ROOT:
    raise ValueError("PROJECT_ROOT 가 .env에 설정되어 있지 않습니다.")
PROJECT_ROOT = Path(PROJECT_ROOT).resolve()

if not FRONT_PROJECT_ROOT:
    raise ValueError("FRONT_PROJECT_ROOT 가 .env에 설정되어 있지 않습니다.")

# Google / OpenAI 클라이언트
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
openai_client = OpenAI()

# 이미지 생성에 사용할 모델 (image-to-image)
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"


# --------------------------------------------------
# 공통 이미지 헬퍼
# --------------------------------------------------
def _read_and_encode_image_for_gemini(image_path: str) -> types.Part:
    """
    Google Gemini용 이미지 입력 (inline_data Blob).
    - image_path를 읽어서 types.Part(inline_data=types.Blob)로 변환.
    """
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"이미지 파일이 존재하지 않습니다: {image_path}")

    mime_type = "image/jpeg"
    if p.suffix.lower() == ".png":
        mime_type = "image/png"

    with open(p, "rb") as f:
        image_bytes = f.read()

    return types.Part(
        inline_data=types.Blob(
            data=image_bytes,
            mime_type=mime_type,
        )
    )


def _encode_image_to_small_data_url(image_path: str, max_size: int = 256, quality: int = 60) -> str:
    """
    OpenAI Vision 입력용: 이미지를 작은 썸네일로 줄여
    data:image/jpeg;base64,... 형태로 변환 (TPM 절약용).
    """
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없음: {image_path}")

    img = Image.open(p).convert("RGB")
    img.thumbnail((max_size, max_size), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def _resolve_image_path_from_url(image_url: str, project_id: str | int, prefix: str) -> Path:
    """
    image_url 이
    - http(s)로 시작하면: 다운로드해서 generated_images/{prefix}_{project_id}.png 로 저장
    - /data/... 또는 data/... 이면: FRONT_PROJECT_ROOT/public 기준 상대 경로로 사용
    """
    # http(s) URL → 다운로드
    if image_url.startswith("http://") or image_url.startswith("https://"):
        tmp_dir = Path("generated_images")
        tmp_dir.mkdir(exist_ok=True)
        tmp_path = tmp_dir / f"{prefix}_{project_id}.png"

        print(f"🌐 원격 이미지 다운로드: {image_url}")
        resp = requests.get(image_url, stream=True)
        resp.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return tmp_path

    # 로컬 경로 (프론트 public 기준 상대경로라고 가정)
    front_root = Path(FRONT_PROJECT_ROOT)
    public_root = front_root / "public"

    rel = image_url.lstrip("/")  # 맨 앞 / 제거
    image_path = public_root / rel
    return image_path


# --------------------------------------------------
# 1) LLM: 스타일/레이아웃 + 메타데이터 기반 리플렛 프롬프트 생성
# --------------------------------------------------

LEAFLET_SYSTEM_PROMPT = """
You are a professional festival leaflet prompt designer.

## Goal

Your job is to look at:
- IMAGE 1: a FESTIVAL POSTER style reference,
- IMAGE 2: a LEAFLET LAYOUT reference, and
- FESTIVAL METADATA in JSON (Korean name, period, location, concept, program list),

and generate ONE detailed English prompt for the Google model
`gemini-2.5-flash-image` that will:

- keep the illustration STYLE and color feeling of IMAGE 1,
- adopt the overall LAYOUT structure of IMAGE 2,
- and render a fully finished leaflet image with readable **Korean** text
  (English subtitle is optional).

This leaflet will be used as-is. There will be NO further manual editing.
So text placement, hierarchy, and readability must be carefully planned.

---

## How to use images and metadata

1. IMAGE 1 (style reference)
   - Capture the illustration style (e.g., Santa, winter village, warm lights),
     color palette (navy blue, gold, warm light), and overall atmosphere.
   - Ask the model to **match this style closely** for the leaflet.

2. IMAGE 2 (layout reference)
   - Read the column and section structure (e.g., 4 columns: main poster, programs, schedule, map/info).
   - Ask the model to adopt a **similar multi-column layout**:
     - Column 1: main visual / hero area
     - Column 2: key programs
     - Column 3: schedule / timetable
     - Column 4: map & transportation / info
   - You may simplify or slightly adjust the layout,
     but the general idea of separated information columns must remain.

3. FESTIVAL METADATA JSON
   - Use ONLY the given text values for Korean titles and labels.
   - Use program_name list to decide 3–4 main programs to highlight on the leaflet.
   - Avoid hallucinating new program names or fake sponsors.

---

## Layout (4-panel requirement)

The leaflet MUST be designed as **exactly four vertical panels** inside a 16:9 canvas,
like a 4-cut comic strip.

- The overall aspect ratio is 16:9 (landscape).
- Divide the canvas into four equal-width vertical panels from left to right.
- Separate the panels with thin, elegant vertical gold lines or borders.
- All four panels must have the same height and be clearly distinguishable.

Use the four panels as follows:

- Panel 1 (leftmost): main hero visual and festival title area.
- Panel 2: key programs section.
- Panel 3: schedule / timetable section.
- Panel 4 (rightmost): map, transportation, and venue information section.

Do NOT merge panels or collapse them into fewer columns.
Do NOT create a free-form layout; the four-panel structure is a hard requirement.
The leaflet_prompt you output must explicitly mention this four-panel layout
and the vertical separators.

---

## Text rendering requirements

1. Main title:
   - The Korean title must be clearly readable and visually dominant.
   - Example placement: large hero text in panel 1.

2. Period and location:
   - Show both in Korean, near the title area, with slightly smaller but still strong typography.

3. Program area (panel 2):
   - Show 3–4 bullet-like lines for main programs in Korean (no need for English),
     optionally with small icons that match each program.

4. Schedule area (panel 3):
   - Create a simple timetable style with dates and times,
     but keep it readable and not overly dense.

5. Map / info area (panel 4):
   - Show a simple, stylized map or icon set that suggests the venue and transport,
     and a small area for bus/car information or notes.
   - Text here can be shorter and more symbolic if needed.

6. Very important rules:
   - Korean text must not be deformed; it should look like real Korean typography.
   - Do NOT invent long paragraphs; keep text to short labels, titles, and bullet lists.
   - Do NOT add random English slogans that are not in metadata.
   - The final leaflet MUST NOT be a direct copy of IMAGE 2.
   - It should be a new composition that only follows a similar multi-column structure.
   - Do not replicate exact icons, map details, or text layout one-to-one.

---

## Visual & technical requirements

- Aspect ratio: 16:9, horizontal leaflet.
- High resolution, print-ready feeling.
- Maintain strong contrast for text: navy/dark background + bright text (white/gold).
- Use clean, modern fonts that feel festive but readable.
- Composition should feel like a single, cohesive leaflet, not four separate posters.

---

## Output

You must return ONLY JSON of the following form:

{
  "leaflet_prompt": "<full detailed English prompt for gemini-2.5-flash-image>"
}

- Do NOT include Korean in the JSON keys.
- The `leaflet_prompt` must explicitly mention:
  - that IMAGE 1 is the style reference,
  - that IMAGE 2 is the layout reference,
  - the desired sections (title, period, location, programs, schedule, map/info),
  - the **four vertical panels** and their roles,
  - that clear Korean text must be rendered.
- Do NOT wrap the JSON in backticks or markdown.
"""


def generate_leaflet_image_prompt(
    *,
    style_image_path: str,
    layout_image_path: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
    concept_description: str,
    program_name: Optional[List[str]] = None,
) -> str:
    """
    이미지 2장(스타일/레이아웃) + 메타데이터 기반으로
    gemini-2.5-flash-image용 leaflet_prompt를 하나 생성.
    """
    print("🚀 리플렛 이미지 프롬프트 생성 시작")

    program_name = program_name or []
    programs_block = "\n".join(f"- {name}" for name in program_name)

    meta = {
        "festival_name_ko": festival_name_ko,
        "festival_period_ko": festival_period_ko,
        "festival_location_ko": festival_location_ko,
        "concept_description": concept_description,
        "program_name_list": program_name,
    }
    meta_json = json.dumps(meta, ensure_ascii=False)

    style_data_url = _encode_image_to_small_data_url(style_image_path)
    layout_data_url = _encode_image_to_small_data_url(layout_image_path)

    user_text = (
        "You will receive FESTIVAL METADATA as JSON and TWO reference images:\n"
        "- IMAGE 1: festival poster style reference\n"
        "- IMAGE 2: leaflet layout reference\n\n"
        "Using these, design a single, detailed English prompt for gemini-2.5-flash-image\n"
        "to generate a finished festival leaflet that matches style 1 and layout 2.\n"
        "The leaflet must use a 16:9 horizontal canvas divided into FOUR equal-width\n"
        "vertical panels (panel 1: hero & title, panel 2: programs, panel 3: schedule,\n"
        "panel 4: map & transportation), clearly separated by thin vertical gold lines.\n\n"
        "Festival metadata JSON:\n"
        f"{meta_json}\n\n"
        "Program list:\n"
        f"{programs_block}\n"
    )

    resp = openai_client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": LEAFLET_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": style_data_url}},   # IMAGE 1
                    {"type": "image_url", "image_url": {"url": layout_data_url}},  # IMAGE 2
                ],
            },
        ],
    )

    data = json.loads(resp.choices[0].message.content)
    leaflet_prompt = data.get("leaflet_prompt", "").strip()
    if not leaflet_prompt:
        raise ValueError("LLM이 leaflet_prompt를 생성하지 못했습니다.")
    print("✅ 리플렛 프롬프트 생성 완료")
    return leaflet_prompt


# --------------------------------------------------
# 2) Gemini image-to-image: prompt + 이미지2장 → 최종 리플렛 이미지
# --------------------------------------------------
def generate_leaflet_image_with_gemini(
    *,
    leaflet_prompt: str,
    style_image_path: str,
    download_name: str,
) -> Optional[Path]:
    """
    gemini-2.5-flash-image에:
    - leaflet_prompt (텍스트)
    - style_image (IMAGE 1)
    만 전달해서 최종 리플렛 이미지 생성.
    레이아웃 이미지는 GPT 프롬프트 설계에서만 사용하고,
    실제 이미지 생성에는 넣지 않는다.
    """
    print("\n--- Gemini image-to-image 리플렛 생성 시작 ---")

    DOWNLOAD_DIR = Path("generated_images")
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    output_path = DOWNLOAD_DIR / download_name

    style_part = _read_and_encode_image_for_gemini(style_image_path)

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_IMAGE_MODEL,
            contents=[
                leaflet_prompt,      # 텍스트 프롬프트
                style_part,          # 스타일 레퍼런스 레퍼런스
            ],
            # 👇👇👇 16:9 종횡비와 이미지 응답 모달리티를 강제하는 설정 추가 👇👇👇
            config=types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE'], # 이미지와 텍스트 모두 응답 요청
                image_config=types.ImageConfig(
                    aspect_ratio="16:9" # 16:9 비율로 고정
                ),
            )
            # 👆👆👆 16:9 종횡비와 이미지 응답 모달리티를 강제하는 설정 추가 👆👆👆
        )
    except Exception as e:
        print(f"❌ Gemini 이미지 모델 호출 에러: {repr(e)}")
        return None

    try:
        parts = getattr(response, "parts", None)
        if parts is None and getattr(response, "candidates", None):
            parts = response.candidates[0].content.parts

        if not parts:
            print("❌ 응답에서 parts를 찾을 수 없습니다.")
            return None

        saved = False
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is not None and inline.mime_type.startswith("image/"):
                img = part.as_image()
                img.save(output_path)
                print(f"✅ 리플렛 이미지 생성 & 저장 완료: {output_path.resolve()}")
                saved = True
                break

        if not saved:
            print("❌ 이미지 inline_data를 가진 part를 찾지 못했습니다.")
            return None

        return output_path

    except Exception as e:
        print(f"❌ 이미지 디코딩/저장 중 오류: {repr(e)}")
        return None


# --------------------------------------------------
# 3) 메인 엔트리: run_leaflet_image_to_editor
# --------------------------------------------------
def run_leaflet_image_to_editor(
    *,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
    project_id: int | str,
    style_image_url: str,   # 1번 이미지 (포스터 스타일)
    layout_image_url: str,  # 2번 이미지 (리플렛 레이아웃)
    concept_description: str,
    program_name: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    파이프라인:

    1) style_image_url / layout_image_url → 실제 파일 경로 계산
    2) OpenAI LLM으로 gemini-2.5-flash-image용 leaflet_prompt 생성
    3) Gemini image 모델(gemini-2.5-flash-image)로 최종 리플렛 이미지 생성
    4) FRONT_PROJECT_ROOT/public/data/promotion/M000001/{project_id}/image/leaflet_image.png 저장
    5) DB 저장용 dict 반환
    """
    pNo = str(project_id)

    # 1. 이미지 실제 경로
    style_image_path = _resolve_image_path_from_url(style_image_url, pNo, prefix="leaflet_style")
    layout_image_path = _resolve_image_path_from_url(layout_image_url, pNo, prefix="leaflet_layout")

    if not style_image_path.exists():
        raise FileNotFoundError(f"스타일 이미지가 존재하지 않습니다: {style_image_path}")
    if not layout_image_path.exists():
        raise FileNotFoundError(f"레이아웃 이미지가 존재하지 않습니다: {layout_image_path}")

    # 2. 프롬프트 생성
    leaflet_prompt = generate_leaflet_image_prompt(
        style_image_path=str(style_image_path),
        layout_image_path=str(layout_image_path),
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
        concept_description=concept_description,
        program_name=program_name,
    )

    # 3. Gemini image-to-image 생성
    final_temp = generate_leaflet_image_with_gemini(
        leaflet_prompt=leaflet_prompt,
        style_image_path=str(style_image_path),
        download_name=f"leaflet_image_{pNo}.png",
    )

    if not final_temp:
        raise RuntimeError("Gemini 리플렛 이미지 생성이 실패했습니다.")

    # 4. FRONT public/data/promotion/M000001/{pNo}/image/leaflet_image.png 로 이동
    front_root = Path(FRONT_PROJECT_ROOT)
    public_root = front_root / "public"
    rel_dir = Path("data") / "promotion" / PROMOTION_CODE / pNo / "image"
    target_dir = public_root / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / "leaflet_image.png"
    shutil.move(str(final_temp), target_path)
    print(f"✅ 최종 리플렛 이미지 저장: {target_path}")

    # 5. DB 반환값
    db_rel_path = (
        Path("data") / "promotion" / PROMOTION_CODE / pNo / "image" / "leaflet_image.png"
    ).as_posix()

    result: Dict[str, Any] = {
        "db_file_type": "leaflet_image",
        "type": "image",
        "db_file_path": db_rel_path,
        "type_ko": "리플렛 이미지",
    }
    print("📦 DB 반환값:", result)
    return result


# --------------------------------------------------
# 4) 간단 테스트
# --------------------------------------------------
if __name__ == "__main__":
    """
    예시:
    - style_image_url: 담양 산타 포스터 (스타일)
    - layout_image_url: 네가 방금 올린 리플렛 예시 같은 이미지 (레이아웃)
    """

    # 프론트 public 기준 상대 경로 예시
    test_style_image_url = "data/promotion/M000001/23/poster/poster_1764724850_3.png"
    # 리플렛 레이아웃 레퍼런스는 일단 public 어딘가에 넣어둔다고 가정
    test_layout_image_url = "data/promotion/M000001/25/poster/good_2.jpg"

    try:
        result = run_leaflet_image_to_editor(
            festival_name_ko="제7회 담양 산타 축제",
            festival_period_ko="2025.12.23 ~ 2025.12.24",
            festival_location_ko="메타랜드 일원",
            project_id=25,
            style_image_url=test_style_image_url,
            layout_image_url=test_layout_image_url,
            concept_description="크리스마스, 산타, 따뜻한 조명, 겨울 시즌 축제",
            program_name=[
                "산타 퍼레이드",
                "크리스마스 마켓",
                "야간 빛 축제",
                "산타 빌리지 체험",
            ],
        )

        print("\n✅ 리플렛 파이프라인 실행 완료")
        print("결과 반환값 (DB 저장용 메타데이터):")
        print(result)

    except Exception as e:
        print("\n❌ 테스트 실행 중 오류 발생:")
        print(repr(e))
