"""
에디터 준비: 생성된 이미지에서 글자를 지운 배경(clean/*.png)을 만든다 (여러 장 배치 처리)

글자 지우기 방식
  - CLIPDROP_API_KEY 가 있으면 ClipDrop remove-text
  - 없으면 TEXT_REMOVAL_PROVIDER 의 이미지 편집 모델
      replicate(기본) : REPLICATE_API_TOKEN 으로 Replicate (TEXT_REMOVAL_MODEL, 기본 google/nano-banana)
      gemini          : GEMINI_API_KEY 로 구글에 직접 (기본 gemini-2.5-flash-image). 결제 연결 필요, 실패 시 Replicate
    두 키 모두 다른 기능에 이미 쓰고 있어 새 키가 필요 없다.

환경변수:
    CLIPDROP_API_KEY=      (선택)
    TEXT_REMOVAL_PROVIDER= (선택, gemini | replicate)
    TEXT_REMOVAL_MODEL=    (선택)
"""

import os
from typing import Dict
import json
import cv2
import numpy as np
from PIL import Image  # 확장용으로 남겨둠
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
CLIPDROP_API_KEY = os.getenv("CLIPDROP_API_KEY")

# 🔧 경로 기본값
# app/data/editor/<run_id>/ 구조 기준
from app.core.config import EDITOR_ROOT_DIR as _EDITOR_ROOT, TEXT_REMOVAL_PROVIDER, TEXT_REMOVAL_MODEL, OPENAI_TEXT_MODEL
EDITOR_ROOT_DIR = str(_EDITOR_ROOT)
OUTPUT_ROOT_DIR = r"./output_editor"  # 지금은 안 쓰지만, 혹시 몰라서 남겨둠


# ==============================
# 2. ClipDrop remove-text 호출
# ==============================
def call_clipdrop_remove_text(image_path: str, output_image_path: str) -> None:
    if not CLIPDROP_API_KEY:
        raise RuntimeError("CLIPDROP_API_KEY 비어있음")

    url = "https://clipdrop-api.co/remove-text/v1"
    headers = {"x-api-key": CLIPDROP_API_KEY}

    with open(image_path, "rb") as image_file_object:
        files = {
            "image_file": (
                os.path.basename(image_path),
                image_file_object,
                "image/png",
            )
        }

        r = requests.post(url, files=files, headers=headers)

    if r.ok:
        os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
        with open(output_image_path, "wb") as out:
            out.write(r.content)
        print(f"[CLIPDROP] remove-text saved to: {output_image_path}")
    else:
        print("[CLIPDROP ERROR]", r.status_code, r.text)
        r.raise_for_status()


# ==============================
# 2-1. Replicate 이미지 편집 모델로 글자 지우기 (ClipDrop 대체)
# ==============================
# Gemini 실패 시 대체로 쓰는 Replicate 모델 (같은 계열)
REPLICATE_TEXT_REMOVAL_MODEL = os.getenv("REPLICATE_TEXT_REMOVAL_MODEL", "google/nano-banana")

TEXT_REMOVAL_PROMPT = (
    "Remove all text from this image: titles, letters, numbers, dates and captions. "
    "Fill the removed areas naturally so they match the surrounding background. "
    "Keep everything else exactly the same: composition, colors, illustrations, characters and layout. "
    "Do not add any new elements."
)


def call_replicate_remove_text(image_path: str, output_image_path: str) -> None:
    import replicate

    # TEXT_REMOVAL_MODEL 이 Gemini 모델명(대체 경로)이면 Replicate 기본 모델을 쓴다
    model = TEXT_REMOVAL_MODEL if "/" in TEXT_REMOVAL_MODEL else REPLICATE_TEXT_REMOVAL_MODEL
    print(f"[TEXT-REMOVAL] {model}(Replicate) 로 글자 지우기: {image_path}")
    with open(image_path, "rb") as image_file:
        output = replicate.run(
            model,
            input={
                "prompt": TEXT_REMOVAL_PROMPT,
                "image_input": [image_file],
                "aspect_ratio": "match_input_image",
                "output_format": "png",
            },
        )
    if isinstance(output, list):
        output = output[0]
    data = output.read() if hasattr(output, "read") else requests.get(str(output), timeout=120).content

    os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
    with open(output_image_path, "wb") as out:
        out.write(data)

    _match_size(image_path, output_image_path)
    print(f"[TEXT-REMOVAL] saved to: {output_image_path}")


def image_has_text(image_path: str) -> bool:
    """
    비전 모델로 이미지에 글자가 있는지만 확인한다 (작게 줄여 보내 비용 최소화).
    지시형 편집 모델은 지울 글자가 없으면 장식 요소를 대신 지우기도 해서, 글자가 없으면 편집하지 않는다.
    판단에 실패하면 True (기존처럼 지우기 시도).
    """
    import base64
    import io
    from openai import OpenAI

    try:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            im.thumbnail((768, 768))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()
        res = OpenAI().chat.completions.create(
            model=OPENAI_TEXT_MODEL,
            temperature=0,
            max_tokens=3,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Does this image contain any visible text, letters or numbers? Answer only yes or no."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}},
                ],
            }],
        )
        answer = (res.choices[0].message.content or "").strip().lower()
        print(f"[TEXT-REMOVAL] 글자 유무 판단: {answer!r} ({os.path.basename(image_path)})")
        return not answer.startswith("no")
    except Exception as e:
        print(f"[TEXT-REMOVAL] 글자 유무 판단 실패, 지우기 진행: {e}")
        return True


def call_gemini_remove_text(image_path: str, output_image_path: str) -> None:
    from google import genai
    from google.genai import types

    print(f"[TEXT-REMOVAL] {TEXT_REMOVAL_MODEL}(Gemini) 로 글자 지우기: {image_path}")
    with Image.open(image_path) as src:
        src_img = src.convert("RGB")
    # 클라이언트를 변수에 담아 둔다 (바로 호출하면 요청 전에 정리되어 'client has been closed')
    client = genai.Client()
    res = client.models.generate_content(
        model=TEXT_REMOVAL_MODEL,
        contents=[TEXT_REMOVAL_PROMPT, src_img],
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    data = None
    for part in (res.candidates[0].content.parts if res.candidates else []):
        if getattr(part, "inline_data", None) and part.inline_data.data:
            data = part.inline_data.data
            break
    if data is None:
        raise RuntimeError(f"Gemini 가 이미지를 돌려주지 않았습니다: {getattr(res, 'text', '')!r}")

    os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
    with open(output_image_path, "wb") as out:
        out.write(data)
    _match_size(image_path, output_image_path)
    print(f"[TEXT-REMOVAL] saved to: {output_image_path}")


def _match_size(src_path: str, out_path: str) -> None:
    # 에디터는 원본 좌표에 글자를 다시 올리므로 원본과 크기가 같아야 한다
    with Image.open(src_path) as src, Image.open(out_path) as cleaned:
        if cleaned.size != src.size:
            print(f"[TEXT-REMOVAL] 크기 보정 {cleaned.size} → {src.size}")
            cleaned.convert("RGBA").resize(src.size, Image.LANCZOS).save(out_path, "PNG")


def remove_text(image_path: str, output_image_path: str) -> None:
    """ClipDrop 키가 있으면 ClipDrop, 없으면 TEXT_REMOVAL_PROVIDER(gemini/replicate)로 글자를 지운다."""
    if CLIPDROP_API_KEY:
        call_clipdrop_remove_text(image_path, output_image_path)
        return
    # 지시형 편집 모델은 글자가 없는 이미지를 망가뜨릴 수 있어, 글자가 있을 때만 편집한다
    if not image_has_text(image_path):
        os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
        with Image.open(image_path) as im:
            im.save(output_image_path, "PNG")
        print(f"[TEXT-REMOVAL] 글자 없음 → 원본 사용: {output_image_path}")
        return
    if TEXT_REMOVAL_PROVIDER == "replicate":
        call_replicate_remove_text(image_path, output_image_path)
        return
    try:
        call_gemini_remove_text(image_path, output_image_path)
    except Exception as e:
        # 무료 등급 키는 이미지 모델 한도가 없어 429(RESOURCE_EXHAUSTED)가 난다 → 결제가 연결된 Replicate 로 대체
        if not os.getenv("REPLICATE_API_TOKEN"):
            raise
        print(f"[TEXT-REMOVAL] Gemini 실패 → Replicate 로 대체: {str(e)[:120]}")
        call_replicate_remove_text(image_path, output_image_path)


# ==============================
# 3. 한 장 처리 유닛 (type 기반)
# ==============================
def process_poster(
    image_path: str,
    editor_run_root: str,
    type_name: str,
) -> Dict[str, str]:
    """
    before_image 안에 있는 한 장의 이미지를 받아서
    - 글자 지우기 (ClipDrop 또는 Replicate)
    - app/data/editor/<run_id>/clean/<type_name>.png 로 저장
    """

    clean_dir = os.path.join(editor_run_root, "clean")
    os.makedirs(clean_dir, exist_ok=True)

    cleaned_path = os.path.join(clean_dir, f"{type_name}.png")

    remove_text(image_path, cleaned_path)

    return {
        "type": type_name,
        "original": image_path,
        "cleaned": cleaned_path,
    }


# ==============================
# 4. 배치 실행 엔트리 (run_id 단위, before_image 기준)
# ==============================
def run(
    run_id: int,
    editor_root: str = EDITOR_ROOT_DIR,
) -> Dict[str, Dict[str, str]]:
    """
    주어진 run_id에 대해:

      - editor/<run_id>/before_image/*.png (또는 jpg 등)을 모두 순회
      - 각 이미지 파일에 대해 글자 지우기 실행 (ClipDrop 또는 Replicate)
      - 결과 이미지를 editor/<run_id>/clean/<파일이름>.png 로 저장

    리턴값:
      {
        "road_banner": {
          "type": "road_banner",
          "original": "C:\\...\\before_image\\road_banner.png",
          "cleaned":  "C:\\...\\editor\\<run_id>\\clean\\road_banner.png"
        },
        "streetlamp_banner": { ... },
        ...
      }
    """
    editor_run_root = os.path.join(editor_root, str(run_id))

    if not os.path.isdir(editor_run_root):
        raise FileNotFoundError(f"editor run folder not found: {editor_run_root}")

    # ✅ 이 스크립트는 before_image 폴더 안에 있는 실제 이미지(.png)를 돈다
    before_image_dir = os.path.join(editor_run_root, "before_image")

    if not os.path.isdir(before_image_dir):
        raise FileNotFoundError(f"before_image dir not found: {before_image_dir}")

    # before_image 안의 이미지 파일들 순회
    image_files = [
        f for f in os.listdir(before_image_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    ]
    image_files.sort()

    if not image_files:
        print(f"[RUN] no image files found in {before_image_dir}")
        return {}

    results: Dict[str, Dict[str, str]] = {}

    for filename in image_files:
        image_path = os.path.join(before_image_dir, filename)
        stem = Path(filename).stem  # 확장자 제거한 이름 → type_name으로 사용

        type_name = stem  # ex) road_banner, streetlamp_banner 등

        print(
            f"\n=== Processing run_id={run_id}, "
            f"type={type_name}, image_file={filename} ==="
        )

        result_paths = process_poster(
            image_path=image_path,
            editor_run_root=editor_run_root,
            type_name=type_name,
        )

        results[type_name] = result_paths

    return results


# ==============================
# 5. 테스트 전용 main
# ==============================
if __name__ == "__main__":
    # 테스트할 때만 직접 호출
    TEST_RUN_ID = 5
    run(TEST_RUN_ID)
