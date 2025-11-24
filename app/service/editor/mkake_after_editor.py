"""
배너 템플릿용 TextBox 레이아웃 생성 파이프라인

입력:
  - editor/<run_id>/before_data/{type}.json   (메타데이터)
  - output_editor/<run_id>/ocr/{type}.json    (OCR 결과)
  - meta["image_path"]                        (영어 placeholder 이미지)

출력:
  - output_editor/<run_id>/layout/{type}.json

동작 개요:
  1) 메타데이터 + OCR + 원본 이미지를 LLM(비전)에게 넘겨서
     - 어떤 OCR id가 이름/기간/장소인지
     - 각 라인의 정렬(left/center/right)이 뭔지 판단
  2) PaddleOCR가 내부에서 리사이즈한 좌표계(예: 4000×1000)를
     원본 캔버스(예: 4096×1024) 좌표계로 역스케일링
  3) 최종 TextBox(left, top, width, fontSize 등)를 생성해서
     canvasData 형태로 저장
"""

import os
import json
import base64
import mimetypes
from pathlib import Path
from typing import List, Literal, Dict, Any

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
load_dotenv()

# =========================
# 0) 프로젝트 경로 기본값
# =========================

EDITOR_ROOT_DIR = r"C:\final_project\ACC\acc-ai\app\data\editor"
OUTPUT_ROOT_DIR = r"./output_editor"


# =========================
# 1) 에디터용 TextBox / Canvas 모델
# =========================

class TextBox(BaseModel):
    type: Literal["textbox"] = "textbox"
    text: str

    left: float
    top: float
    width: float

    fontSize: float
    fontFamily: str = "Arial"
    fill: str = "#111827"
    textAlign: Literal["left", "center", "right"] = "left"


class CanvasData(BaseModel):
    width: int
    height: int
    objects: List[TextBox]


class TemplateLayout(BaseModel):
    type: str
    canvasData: CanvasData


# =========================
# 2) LLM이 판단해줄 매핑 구조
# =========================

class LayoutMapping(BaseModel):
    """LLM이 OCR id를 semantic field에 매핑해주는 결과."""
    festival_name_box_id: int = Field(
        ..., description="축제 이름이 들어간 OCR 박스 id"
    )
    festival_period_box_id: int = Field(
        ..., description="축제 기간이 들어간 OCR 박스 id"
    )
    festival_location_box_id: int = Field(
        ..., description="축제 장소가 들어간 OCR 박스 id"
    )

    festival_name_align: Literal["left", "center", "right"] = "center"
    festival_period_align: Literal["left", "center", "right"] = "center"
    festival_location_align: Literal["left", "center", "right"] = "center"


# =========================
# 3) 로컬 이미지를 data:URL(base64)로 변환
# =========================

def local_image_to_data_url(image_path: str) -> str:
    """
    OpenAI vision 모델에 로컬 이미지를 보내기 위해
    data:<mime>;base64,... 형식으로 인코딩.
    """
    mime, _ = mimetypes.guess_type(image_path)
    if mime is None:
        mime = "image/png"

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    return f"data:{mime};base64,{b64}"


# =========================
# 4) LLM: 이미지 + OCR + 메타데이터로 매핑 판단
# =========================

llm = ChatOpenAI(
    model="gpt-4.1-mini",   # 필요하면 gpt-4.1, gpt-4.1-mini, gpt-5.1 등으로 변경
    temperature=0,
)


def get_layout_mapping_with_llm(
    meta: Dict[str, Any],
    ocr_result: Dict[str, Any],
    image_path: str,
) -> LayoutMapping:
    """
    - meta: before_data/{type}.json 파싱한 dict
    - ocr_result: output_editor/.../ocr/{type}.json 파싱한 dict
    - image_path: meta["image_path"]
    """

    image_data_url = local_image_to_data_url(image_path)
    ocr_items = ocr_result.get("ocr_results", [])

    system_msg = SystemMessage(
        content=(
            "너는 축제 포스터/배너 레이아웃을 분석하는 디자이너이자 엔지니어야. "
            "이미지, OCR 결과, 메타데이터를 보고 어떤 텍스트 라인이 "
            "축제 이름 / 축제 기간 / 축제 장소인지 골라서 매핑해줘."
        )
    )

    prompt_text = f"""
다음은 배너 템플릿의 메타데이터와 OCR 결과야.

[METADATA]
{json.dumps(meta, ensure_ascii=False, indent=2)}

[설명]
- festival_base_name_placeholder: 최종 한국어 축제 이름 텍스트
- festival_base_period_placeholder: 최종 한국어 축제 기간 텍스트
- festival_base_location_placeholder: 최종 한국어 축제 장소 텍스트

[OCR_RESULTS]
아래 리스트의 각 항목은 하나의 텍스트 라인이고,
id / text / score / bbox(x,y,w,h)를 가진다:

{json.dumps(ocr_items, ensure_ascii=False, indent=2)}

해야 할 일:
1. ocr_results의 각 text를 보고,
   - 축제 이름에 해당하는 id
   - 축제 기간에 해당하는 id
   - 축제 장소에 해당하는 id
   를 골라라.
2. 각 라인이 포스터에서 좌우로 봤을 때
   - left / center / right 중 어디 정렬인지 판단해라.
3. 아래 JSON 형식으로만 답해라:

{{
  "festival_name_box_id": number,
  "festival_period_box_id": number,
  "festival_location_box_id": number,
  "festival_name_align": "left|center|right",
  "festival_period_align": "left|center|right",
  "festival_location_align": "left|center|right"
}}

설명 텍스트는 쓰지 말고, 유효한 JSON만 출력해.
"""

    human_msg = HumanMessage(
        content=[
            {"type": "text", "text": prompt_text},
            {
                "type": "image_url",
                "image_url": {"url": image_data_url},
            },
        ]
    )

    resp = llm.invoke([system_msg, human_msg])
    raw = resp.content  # 모델이 출력한 JSON 문자열
    mapping = LayoutMapping.model_validate_json(raw)
    return mapping


# =========================
# 5) OCR 좌표계 크기 추정 + 원본 좌표로 재스케일
# =========================

def guess_ocr_space_size(ocr_result: Dict[str, Any],
                         image_size: Dict[str, int]) -> Dict[str, float]:
    """
    OCR bbox(x,y,w,h)들을 보고, PaddleOCR가 사용한
    내부 좌표계의 최대 width/height를 추정.
    (예: 4096 -> 4000, 1024 -> 1000 으로 리사이즈했다면
     width ≈ 4000, height ≈ 1000 근처로 나온다)
    """
    xs2 = []
    ys2 = []

    for item in ocr_result.get("ocr_results", []):
        bbox = item.get("bbox") or []
        if len(bbox) != 4:
            continue
        x, y, w, h = bbox
        xs2.append(x + w)
        ys2.append(y + h)

    if not xs2 or not ys2:
        # 박스가 없으면 그냥 원본 이미지 사이즈 사용
        return {
            "width": float(image_size["width"]),
            "height": float(image_size["height"]),
        }

    max_x2 = max(xs2)
    max_y2 = max(ys2)

    return {"width": float(max_x2), "height": float(max_y2)}


def rescale_bbox_to_canvas(
    bbox: List[int],
    canvas_size: Dict[str, int],   # 예: {"width": 4096, "height": 1024}
    ocr_space: Dict[str, float],   # 예: {"width": 4000.0, "height": 1000.0}
) -> List[float]:
    """
    OCR 좌표계 기준 bbox를, 최종 캔버스 좌표계로 재스케일.

    - bbox: [x, y, w, h] (OCR 내부 좌표, 최대값이 대략 ocr_space width/height)
    - canvas_size: 우리가 editor에 넘길 최종 캔버스 사이즈
    """
    x, y, w, h = bbox

    sx = canvas_size["width"] / ocr_space["width"]
    sy = canvas_size["height"] / ocr_space["height"]

    x2 = x * sx
    y2 = y * sy
    w2 = w * sx
    h2 = h * sy

    return [x2, y2, w2, h2]


# =========================
# 6) OCR id → 아이템 찾기, bbox → TextBox 변환
# =========================

def _find_ocr_item_by_id(
    ocr_result: Dict[str, Any],
    box_id: int
) -> Dict[str, Any]:
    for item in ocr_result.get("ocr_results", []):
        if int(item.get("id")) == int(box_id):
            return item
    raise ValueError(f"OCR id={box_id} not found")


def _bbox_to_textbox(
    bbox: List[float],
    text: str,
    align: Literal["left", "center", "right"],
    font_color: str,
    font_family: str,
    size_scale: float = 0.8,
    extra_width_ratio: float = 1.2,
) -> TextBox:
    """
    - bbox: [x, y, w, h] (이미 "캔버스 좌표계"로 재스케일된 값)
    - left/top: x,y 그대로
    - width: w * extra_width_ratio  (양옆 여유)
    - fontSize: h * size_scale      (bbox 높이 기반 폰트 크기)
    """
    x, y, w, h = bbox

    left = float(x)
    top = float(y)
    width = float(w) * extra_width_ratio
    font_size = float(h) * size_scale

    return TextBox(
        text=text,
        left=left,
        top=top,
        width=width,
        fontSize=font_size,
        fontFamily=font_family,
        fill=font_color,
        textAlign=align,
    )


# =========================
# 7) 한 type 에 대한 TemplateLayout 생성
# =========================

def build_template_layout_for_type(
    run_id: int,
    type_name: str,
    editor_root: str = EDITOR_ROOT_DIR,
    output_root: str = OUTPUT_ROOT_DIR,
) -> TemplateLayout:
    """
    - editor/<run_id>/before_data/{type}.json
    - output_editor/<run_id>/ocr/{type}.json
    - meta.image_path (원본 영어 placeholder 이미지)

    를 기반으로 TemplateLayout(canvasData + textbox들) 생성.
    """

    # ---- 1) 경로 세팅 ----
    before_data_path = (
        Path(editor_root)
        / str(run_id)
        / "before_data"
        / f"{type_name}.json"
    )
    ocr_json_path = (
        Path(output_root)
        / str(run_id)
        / "ocr"
        / f"{type_name}.json"
    )

    if not before_data_path.exists():
        raise FileNotFoundError(f"before_data not found: {before_data_path}")
    if not ocr_json_path.exists():
        raise FileNotFoundError(f"OCR json not found: {ocr_json_path}")

    # ---- 2) JSON 로드 ----
    meta = json.loads(before_data_path.read_text(encoding="utf-8"))
    ocr_result = json.loads(ocr_json_path.read_text(encoding="utf-8"))

    # 원본 이미지 사이즈 (export_ocr_for_gpt 에서 넣어둔 값)
    image_size = ocr_result["image_size"]  # {"width": 4096, "height": 1024} 같은 형태

    # ✅ 최종 캔버스 사이즈:
    #   - 우선 meta["width"/"height"] 사용
    #   - 없으면 image_size 사용
    canvas_w = int(meta.get("width", image_size["width"]))
    canvas_h = int(meta.get("height", image_size["height"]))
    canvas_size = {"width": canvas_w, "height": canvas_h}

    # 최종 한국어 텍스트
    festival_name = meta.get("festival_base_name_placeholder", "")
    festival_period = meta.get("festival_base_period_placeholder", "")
    festival_location = meta.get("festival_base_location_placeholder", "")

    # 색/폰트 (없으면 기본값)
    name_color = meta.get("festival_color_name_placeholder", "#FFFFFF")
    period_color = meta.get("festival_color_period_placeholder", "#FFFFFF")
    location_color = meta.get("festival_color_location_placeholder", "#FFFFFF")

    name_font = meta.get("festival_font_name_placeholder", "Arial")
    period_font = meta.get("festival_font_period_placeholder", "Arial")
    location_font = meta.get("festival_font_location_placeholder", "Arial")

    # ---- 3) LLM으로 OCR id 매핑 + 정렬 판단 ----
    image_path = meta["image_path"]
    mapping = get_layout_mapping_with_llm(
        meta=meta,
        ocr_result=ocr_result,
        image_path=image_path,
    )

    # ---- 4) OCR 좌표계 크기 추정 (예: 4000×1000) ----
    ocr_space = guess_ocr_space_size(ocr_result, image_size=image_size)

    # ---- 5) 매핑 결과 + OCR bbox → 원본 캔버스 좌표 bbox ----
    name_item = _find_ocr_item_by_id(ocr_result, mapping.festival_name_box_id)
    period_item = _find_ocr_item_by_id(ocr_result, mapping.festival_period_box_id)
    location_item = _find_ocr_item_by_id(
        ocr_result,
        mapping.festival_location_box_id,
    )

    name_bbox_orig = rescale_bbox_to_canvas(
        name_item["bbox"],
        canvas_size=canvas_size,
        ocr_space=ocr_space,
    )
    period_bbox_orig = rescale_bbox_to_canvas(
        period_item["bbox"],
        canvas_size=canvas_size,
        ocr_space=ocr_space,
    )
    location_bbox_orig = rescale_bbox_to_canvas(
        location_item["bbox"],
        canvas_size=canvas_size,
        ocr_space=ocr_space,
    )

    # ---- 6) 최종 TextBox 생성 ----
    name_tb = _bbox_to_textbox(
        bbox=name_bbox_orig,
        text=festival_name,
        align=mapping.festival_name_align,
        font_color=name_color,
        font_family=name_font,
        size_scale=0.9,
        extra_width_ratio=1.3,
    )

    period_tb = _bbox_to_textbox(
        bbox=period_bbox_orig,
        text=festival_period,
        align=mapping.festival_period_align,
        font_color=period_color,
        font_family=period_font,
        size_scale=0.7,
        extra_width_ratio=1.3,
    )

    location_tb = _bbox_to_textbox(
        bbox=location_bbox_orig,
        text=festival_location,
        align=mapping.festival_location_align,
        font_color=location_color,
        font_family=location_font,
        size_scale=0.8,
        extra_width_ratio=1.3,
    )

    canvas = CanvasData(
        width=canvas_w,
        height=canvas_h,
        objects=[name_tb, period_tb, location_tb],
    )

    return TemplateLayout(
        type=type_name,
        canvasData=canvas,
    )


# =========================
# 8) 레이아웃 JSON 저장 유틸
# =========================

def save_template_layout_json(
    layout: TemplateLayout,
    run_id: int,
    output_root: str = OUTPUT_ROOT_DIR,
) -> Path:
    """
    TemplateLayout 객체를
    output_editor/<run_id>/layout/{type}.json 으로 저장.
    """
    layout_dir = Path(output_root) / str(run_id) / "layout"
    layout_dir.mkdir(parents=True, exist_ok=True)

    out_path = layout_dir / f"{layout.type}.json"
    out_path.write_text(
        json.dumps(layout.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[LAYOUT] saved layout for type='{layout.type}' to: {out_path}")
    return out_path


def build_and_save_layout_for_type(
    run_id: int,
    type_name: str,
    editor_root: str = EDITOR_ROOT_DIR,
    output_root: str = OUTPUT_ROOT_DIR,
) -> Path:
    """
    1) build_template_layout_for_type → layout(dict) 생성
    2) output_editor/<run_id>/layout/{type}.json 저장
    3) 파일 경로 반환
    """
    layout = build_template_layout_for_type(
        run_id=run_id,
        type_name=type_name,
        editor_root=editor_root,
        output_root=output_root,
    )

    # layout(dict)을 그대로 JSON으로 저장
    return save_template_layout_json(
        layout,
        run_id=run_id,
        output_root=output_root,
    )


def build_and_save_all_layouts_for_run(
    run_id: int,
    editor_root: str = EDITOR_ROOT_DIR,
    output_root: str = OUTPUT_ROOT_DIR,
) -> Dict[str, str]:
    """
    - editor/<run_id>/before_data/*.json 스캔해 type 리스트 획득
    - 각 type에 대해 레이아웃 생성 + 저장
    - {type: layout_json_path} 딕셔너리 반환
    """
    before_data_dir = Path(editor_root) / str(run_id) / "before_data"
    if not before_data_dir.is_dir():
        raise FileNotFoundError(f"before_data dir not found: {before_data_dir}")

    json_files = sorted(
        [p for p in before_data_dir.iterdir() if p.suffix.lower() == ".json"]
    )
    if not json_files:
        print(f"[LAYOUT] no metadata json found in {before_data_dir}")
        return {}

    results: Dict[str, str] = {}

    for meta_path in json_files:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        type_name = meta.get("type") or meta_path.stem

        print(f"\n[LAYOUT] build & save for run_id={run_id}, type={type_name}")

        # 레이아웃(dict) 생성
        layout = build_template_layout_for_type(
            run_id=run_id,
            type_name=type_name,
            editor_root=editor_root,
            output_root=output_root,
        )

        # JSON 저장
        out_path = save_template_layout_json(
            layout,
            run_id=run_id,
            output_root=output_root,
        )

        results[type_name] = str(out_path)

    # index.json 저장
    layout_index_path = (
        Path(output_root) / str(run_id) / "layout" / "index.json"
    )
    layout_index_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[LAYOUT] layout index saved to: {layout_index_path}")

    return results


# =========================
# 9) 테스트용 main
# =========================

if __name__ == "__main__":
    TEST_RUN_ID = 2  # 네가 쓰는 run_id로 바꿔서 테스트
    build_and_save_all_layouts_for_run(run_id=TEST_RUN_ID)
