import os
import json
from pathlib import Path
from typing import List, Dict, Any
# app/data/editor/<run_id>/ 기준 루트 폴더
EDITOR_ROOT_DIR = r"C:\final_project\ACC\acc-ai\app\data\editor"

# 템플릿이 들어있는 폴더
LAYOUT_TEMPLATES_DIR = Path(EDITOR_ROOT_DIR) / "layout_templates"

# FastAPI 에서 mount 한 static URL prefix
# 예: app.mount("/static/editor", StaticFiles(directory="app/data/editor"), name="editor_static")
STATIC_BASE_URL = "http://127.0.0.1:5000/static/editor"


def build_total_layout(
    run_id: int,
    editor_root: str = EDITOR_ROOT_DIR,
    static_base_url: str = STATIC_BASE_URL,
) -> List[Dict[str, Any]]:
    """
    1) app/data/editor/<run_id>/before_data/*.json 읽기
    2) app/data/editor/layout_templates/<type>.json 로드
    3) role 에 맞게 before_data 의 텍스트만 템플릿에 주입
    4) clean 이미지(static URL)를 backgroundImageUrl 에 주입
    5) app/data/editor/<run_id>/layout/total.json 생성

    total.json 구조 (최상위가 배열):
    [
      { "id": 1, "type": "...", "backgroundImageUrl": "...", "canvasData": {...} },
      { "id": 2, ... },
      ...
    ]
    """

    run_dir = Path(editor_root) / str(run_id)
    before_dir = run_dir / "before_data"
    clean_dir = run_dir / "clean"
    layout_dir = run_dir / "layout"

    if not before_dir.is_dir():
        raise FileNotFoundError(f"before_data dir not found: {before_dir}")

    if not LAYOUT_TEMPLATES_DIR.is_dir():
        raise FileNotFoundError(f"layout_templates dir not found: {LAYOUT_TEMPLATES_DIR}")

    layout_dir.mkdir(parents=True, exist_ok=True)

    items: List[Dict[str, Any]] = []

    # before_data/*.json 순회
    json_files = sorted(
        f for f in before_dir.iterdir()
        if f.is_file() and f.suffix.lower() == ".json"
    )

    if not json_files:
        print(f"[LAYOUT] no before_data json found in {before_dir}")
        # 빈 배열로라도 total.json 만들고 끝냄
        total_path = layout_dir / "total.json"
        total_path.write_text("[]", encoding="utf-8")
        return []

    next_id = 1

    for meta_path in json_files:
        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)

        type_name = meta.get("type") or meta_path.stem

        # 1) 템플릿 로드
        template_path = LAYOUT_TEMPLATES_DIR / f"{type_name}.json"
        if not template_path.is_file():
            # 여기서 스킵되면 total.json 개수가 줄어듦
            print(f"[LAYOUT WARN] template not found for type={type_name}, path={template_path}, skip.")
            continue

        template = json.loads(template_path.read_text(encoding="utf-8"))

        # 2) clean 이미지 경로 -> static URL
        # clean/<type>.png 기준 (이미 remove-text 단계에서 생성됐다고 가정)
        clean_image_path = clean_dir / f"{type_name}.png"
        if not clean_image_path.is_file():
            print(f"[LAYOUT WARN] cleaned image not found for type={type_name}, path={clean_image_path}, skip.")
            continue

        background_image_url = (
            f"{static_base_url}/{run_id}/clean/{clean_image_path.name}"
        )

        # 3) 상단 메타 세팅
        item: Dict[str, Any] = {}

        # 작업공간 id
        item["id"] = next_id
        next_id += 1

        # type, category
        item["type"] = type_name
        if "pro_name" in meta:
            item["category"] = meta["pro_name"]
        else:
            # 템플릿에 category 가 있으면 그거 쓰고, 없으면 빈 문자열
            item["category"] = template.get("category", "")

        # 배경 이미지 URL
        item["backgroundImageUrl"] = background_image_url

        # 4) canvasData는 템플릿에서 그대로 가져오되, text만 meta로 덮어쓰기
        canvas = template.get("canvasData", {})
        objects = canvas.get("objects", [])

        for obj in objects:
            role = obj.get("role")
            if not role:
                continue

            # role 값이 "*festival_name_ko" 또는 "festival_name_ko" 둘 다 대응
            key = role.replace("*", "")
            if key in meta:
                obj["text"] = meta[key]

        item["canvasData"] = canvas

        items.append(item)

    # 5) total.json 저장 (최상위 = 배열)
    total_path = layout_dir / "total.json"
    total_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[LAYOUT] total.json saved to: {total_path}")

    return str(total_path.resolve())


# ✅ 테스트용 (나중에 지워도 됨)
if __name__ == "__main__":
    TEST_RUN_ID = 5
    build_total_layout(TEST_RUN_ID)
