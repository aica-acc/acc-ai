"""
OCR -> ClipDrop remove-text 파이프라인 (배너 여러 장 배치 처리 버전)

필수 라이브러리:
    pip install paddleocr paddlepaddle==2.5.0
    pip install opencv-python pillow requests python-dotenv

환경변수:
    CLIPDROP_API_KEY=your_api_key_here
"""

import os
from typing import List, Dict, Any
import json
import cv2
import numpy as np
from paddleocr import PaddleOCR
from PIL import Image  # 현재는 안 쓰지만, 확장용으로 남겨둠
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
CLIPDROP_API_KEY = os.getenv("CLIPDROP_API_KEY")

# 🔧 경로 기본값 (필요하면 여기만 수정해서 프로젝트 경로 맞추면 됨)
EDITOR_ROOT_DIR = r"C:\final_project\ACC\acc-ai\app\data\editor"
OUTPUT_ROOT_DIR = r"./output_editor"


# ==============================
# 0. OCR 엔진 설정
# ==============================
OCR_ENGINE = PaddleOCR(
    lang="korean",  # 영어도 같이 됨
)


# ==============================
# 1. OCR 관련 유틸
# ==============================
def run_ocr_boxes_only(
    image_path: str,
    min_area: int = 100,
) -> List[Dict[str, Any]]:
    """
    PaddleOCR 3.x .ocr() 결과에서
    텍스트 영역 박스(폴리곤)만 뽑아서 반환.

    리턴 예시:
    [
        {"box": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "area": 1234.5},
        ...
    ]
    """
    result_iter = OCR_ENGINE.ocr(image_path)

    boxes: List[Dict[str, Any]] = []
    total_raw = 0

    for res in result_iter:
        # 1) 파이프라인 Result → dict 추출
        if hasattr(res, "res"):
            data = res.res
        elif isinstance(res, dict) and "res" in res:
            data = res["res"]
        else:
            data = res

        if not isinstance(data, dict):
            print("[OCR] unexpected result type:", type(data))
            return []

        # 2) 폴리곤 후보: rec_polys > dt_polys > rec_boxes
        polys = data.get("rec_polys") or data.get("dt_polys") or data.get("rec_boxes")
        if polys is None:
            print("[OCR] no polys found, keys:", list(data.keys()))
            return []

        polys = np.array(polys)
        total_raw = polys.shape[0]

        # (N, 8) → (N, 4, 2)
        if polys.ndim == 2 and polys.shape[1] == 8:
            polys = polys.reshape(-1, 4, 2)

        for poly in polys:
            pts = np.array(poly, dtype=np.float32)

            if pts.ndim == 1:
                if pts.size % 2 != 0:
                    continue
                pts = pts.reshape(-1, 2)
            elif pts.ndim == 2 and pts.shape[1] != 2:
                try:
                    pts = pts.reshape(-1, 2)
                except Exception:
                    continue

            if pts.shape[0] < 3:
                continue

            try:
                area = cv2.contourArea(pts)
            except Exception:
                continue

            if area < min_area:
                continue

            boxes.append({"box": pts.tolist(), "area": float(area)})

        # 한 이미지 한 번만 처리
        break

    print(f"[OCR] raw polys: {total_raw}, kept after filters: {len(boxes)}")
    return boxes


def debug_ocr_with_text(
    image_path: str,
    min_score: float = 0.75,
    min_area: int = 500,
) -> List[Dict[str, Any]]:
    """
    텍스트 + 점수 + bbox 디버그용.
    score >= min_score, area >= min_area 만 사용.
    """
    result_iter = OCR_ENGINE.ocr(image_path)

    outputs: List[Dict[str, Any]] = []

    for res in result_iter:
        if hasattr(res, "res"):
            data = res.res
        elif isinstance(res, dict) and "res" in res:
            data = res["res"]
        else:
            data = res

        if not isinstance(data, dict):
            print("[OCR] unexpected result type:", type(data))
            return []

        polys = data.get("rec_polys") or data.get("dt_polys") or data.get("rec_boxes")
        if polys is None:
            print("[OCR] no polys found, keys:", list(data.keys()))
            return []

        polys = np.array(polys)
        if polys.ndim == 2 and polys.shape[1] == 8:
            polys = polys.reshape(-1, 4, 2)

        texts = data.get("rec_texts") or data.get("rec_text") or []
        scores = data.get("rec_scores") or data.get("rec_score") or []

        if isinstance(texts, np.ndarray):
            texts = texts.tolist()
        if isinstance(scores, np.ndarray):
            scores = scores.tolist()

        if not isinstance(texts, (list, tuple)):
            texts = [texts]
        if not isinstance(scores, (list, tuple)):
            scores = [scores] * len(texts)

        n = min(polys.shape[0], len(texts), len(scores))

        for i in range(n):
            poly = polys[i]
            txt = str(texts[i])
            try:
                sc = float(scores[i])
            except Exception:
                sc = 1.0

            if sc < min_score:
                continue

            pts = np.array(poly, dtype=np.float32)
            if pts.ndim == 1 and pts.size % 2 == 0:
                pts = pts.reshape(-1, 2)
            elif pts.ndim == 2 and pts.shape[1] != 2:
                try:
                    pts = pts.reshape(-1, 2)
                except Exception:
                    continue

            if pts.shape[0] < 3:
                continue

            area = cv2.contourArea(pts)
            if area < min_area:
                continue

            x, y, w, h = cv2.boundingRect(pts.astype(np.int32))

            info = {
                "index": len(outputs) + 1,
                "text": txt,
                "score": sc,
                "bbox": [x, y, w, h],
                "poly": pts.tolist(),
            }
            outputs.append(info)

            print(
                f"[{info['index']}] text='{txt}'  "
                f"score={sc:.3f}  bbox(x,y,w,h)={x},{y},{w},{h}"
            )

        break

    print(f"[DEBUG] total detections: {len(outputs)}")
    return outputs


def save_debug_ocr_image(
    image_path: str,
    ocr_boxes: List[Dict[str, Any]],
    output_path: str,
) -> None:
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    for idx, b in enumerate(ocr_boxes):
        pts = np.array(b["box"], dtype=np.int32)
        cv2.polylines(img, [pts], isClosed=True, color=(0, 0, 255), thickness=3)

        x, y, w, h = cv2.boundingRect(pts)
        cv2.putText(
            img,
            str(idx + 1),
            (x, max(0, y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2,
        )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(output_path, img)
    print(f"[DEBUG] OCR box overlay saved to: {output_path}")


def export_ocr_for_gpt(
    image_path: str,
    out_json_path: str,
    min_score: float = 0.75,   # ✅ 0.75 이상만 JSON에 저장
    min_area: int = 100,
) -> Dict[str, Any]:
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    h, w = img.shape[:2]

    debug_items = debug_ocr_with_text(
        image_path,
        min_score=min_score,
        min_area=min_area,
    )

    data = {
        "image_size": {"width": w, "height": h},
        "ocr_results": [
            {
                "id": item["index"],
            "text": item["text"],
            "score": float(item["score"]),
            "bbox": item["bbox"],
            }
            for item in debug_items
        ],
    }

    os.makedirs(os.path.dirname(out_json_path), exist_ok=True)
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[EXPORT] OCR for GPT saved to: {out_json_path}")
    return data


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
    out_root_for_run: str,
    type_name: str,
) -> Dict[str, str]:
    """
    한 장의 포스터에 대해:
      - OCR 박스 디버그 이미지
      - GPT용 OCR JSON
      - ClipDrop remove-text 결과
    를 생성하고 경로들을 리턴.

    out_root_for_run: output_editor/<run_id> 같은 경로
    type_name: 메타데이터의 "type" (예: "streetlamp-banner")
    """
    # 폴더 구조:
    #   out_root_for_run/
    #       debug/{type}.png
    #       ocr/{type}.json
    #       clean/{type}.png
    debug_dir = os.path.join(out_root_for_run, "debug")
    ocr_dir = os.path.join(out_root_for_run, "ocr")
    clean_dir = os.path.join(out_root_for_run, "clean")

    os.makedirs(debug_dir, exist_ok=True)
    os.makedirs(ocr_dir, exist_ok=True)
    os.makedirs(clean_dir, exist_ok=True)

    debug_overlay_path = os.path.join(debug_dir, f"{type_name}.png")
    ocr_json_path = os.path.join(ocr_dir, f"{type_name}.json")
    cleaned_path = os.path.join(clean_dir, f"{type_name}.png")

    print(f"[STEP 1] Running OCR (boxes only) for type='{type_name}' ...")
    ocr_boxes = run_ocr_boxes_only(image_path)
    print(f"[STEP 1] detected text boxes: {len(ocr_boxes)}")

    # 2) 폴리곤 디버그 이미지
    save_debug_ocr_image(image_path, ocr_boxes, debug_overlay_path)

    # 3) GPT용 JSON (텍스트 + bbox)
    export_ocr_for_gpt(image_path, ocr_json_path)

    # 4) 텍스트 제거 이미지
    call_clipdrop_remove_text(image_path, cleaned_path)

    return {
        "type": type_name,
        "original": image_path,
        "debug_overlay": debug_overlay_path,
        "ocr_json": ocr_json_path,
        "cleaned": cleaned_path,
    }


# ==============================
# 4. 배치 실행 엔트리 (run_id 단위, before_data 기준)
# ==============================
def run(
    run_id: int,
    editor_root: str = EDITOR_ROOT_DIR,
    output_root: str = OUTPUT_ROOT_DIR,
) -> Dict[str, Dict[str, str]]:
    """
    주어진 run_id에 대해:

      - editor/<run_id>/before_data/*.json 을 모두 순회
      - 각 JSON에서:
          - type: "streetlamp-banner"
          - image_path: "C:\\...\\streetlamp_banner_2025....png"
        를 읽어옴
      - image_path 를 실제 OCR + remove-text 대상으로 사용
      - output_editor/<run_id>/debug/{type}.png
                           /ocr/{type}.json
                           /clean/{type}.png 생성

    리턴값 (index.json 형태):
      {
        "streetlamp-banner": {
          "type": "streetlamp-banner",
          "original": "C:\\...\\streetlamp_banner_XXXX.png",
          "debug_overlay": "./output_editor/<run_id>/debug/streetlamp-banner.png",
          "ocr_json":      "./output_editor/<run_id>/ocr/streetlamp-banner.json",
          "cleaned":       "./output_editor/<run_id>/clean/streetlamp-banner.png"
        },
        ...
      }
    """
    editor_run_root = os.path.join(editor_root, str(run_id))
    before_data_dir = os.path.join(editor_run_root, "before_data")

    if not os.path.isdir(before_data_dir):
        raise FileNotFoundError(f"before_data dir not found: {before_data_dir}")

    output_run_dir = os.path.join(output_root, str(run_id))
    os.makedirs(output_run_dir, exist_ok=True)

    # before_data/*.json 순회
    json_files = [
        f for f in os.listdir(before_data_dir)
        if f.lower().endswith(".json")
    ]
    json_files.sort()

    if not json_files:
        print(f"[RUN] no metadata json found in {before_data_dir}")
        return {}

    results: Dict[str, Dict[str, str]] = {}

    for filename in json_files:
        meta_path = os.path.join(before_data_dir, filename)
        stem = Path(filename).stem

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        # 1) type 이름
        type_name = meta.get("type") or stem

        # 2) 이미지 경로
        image_path = meta.get("image_path")
        if not image_path:
            print(f"[WARN] 'image_path' not found in {meta_path}, skip.")
            continue

        # 상대 경로일 수도 있으니 절대/상대 둘 다 지원
        if not os.path.isabs(image_path):
            # 프로젝트 구조에 맞게 필요하면 여기 조정
            image_path = os.path.abspath(image_path)

        if not os.path.exists(image_path):
            print(f"[WARN] image not found for {type_name}: {image_path}, skip.")
            continue

        print(
            f"\n=== Processing run_id={run_id}, "
            f"type={type_name}, meta_file={filename} ==="
        )

        result_paths = process_poster(
            image_path=image_path,
            out_root_for_run=output_run_dir,
            type_name=type_name,
        )

        # 메타 json 경로도 같이 기록 (LangChain 쪽에서 쓰기 좋게)
        result_paths["before_data"] = meta_path

        results[type_name] = result_paths

    # index.json 저장
    index_json_path = os.path.join(output_run_dir, "index.json")
    with open(index_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[RUN] index saved to: {index_json_path}")

    return results


# ==============================
# 5. 테스트 전용 main
# ==============================
if __name__ == "__main__":
    # 테스트할 때만 직접 호출
    TEST_RUN_ID = 2
    run(TEST_RUN_ID)
