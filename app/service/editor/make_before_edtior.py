"""
OCR -> ClipDrop remove-text 파이프라인 (배너 여러 장 배치 처리 버전)

필수 라이브러리:
    pip install opencv-python pillow requests python-dotenv

환경변수:
    CLIPDROP_API_KEY=your_api_key_here
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
from app.core.config import EDITOR_ROOT_DIR as _EDITOR_ROOT
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
# 3. 한 장 처리 유닛 (type 기반)
# ==============================
def process_poster(
    image_path: str,
    editor_run_root: str,
    type_name: str,
) -> Dict[str, str]:
    """
    before_image 안에 있는 한 장의 이미지를 받아서
    - ClipDrop remove-text 호출
    - app/data/editor/<run_id>/clean/<type_name>.png 로 저장
    """

    clean_dir = os.path.join(editor_run_root, "clean")
    os.makedirs(clean_dir, exist_ok=True)

    cleaned_path = os.path.join(clean_dir, f"{type_name}.png")

    call_clipdrop_remove_text(image_path, cleaned_path)

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
      - 각 이미지 파일에 대해 ClipDrop remove-text 실행
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
