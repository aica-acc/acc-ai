import os
import json
from pathlib import Path
from typing import List, Dict, Any

EDITOR_ROOT_DIR = r"C:\final_project\ACC\acc-ai\app\data\editor"
LAYOUT_TEMPLATES_DIR = Path(EDITOR_ROOT_DIR) / "layout_templates"
STATIC_BASE_URL = "http://127.0.0.1:5000/static/editor"


def build_total_layout(
    run_id: int,
    editor_root: str = EDITOR_ROOT_DIR,
    static_base_url: str = STATIC_BASE_URL,
) -> List[Dict[str, Any]]:

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
        total_path = layout_dir / "total.json"
        total_path.write_text("[]", encoding="utf-8")
        return []

    for meta_path in json_files:
        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)

        type_name = meta.get("type") or meta_path.stem

        # 템플릿 로드
        template_path = LAYOUT_TEMPLATES_DIR / f"{type_name}.json"
        if not template_path.is_file():
            print(f"[LAYOUT WARN] template not found for type={type_name}, path={template_path}, skip.")
            continue

        template = json.loads(template_path.read_text(encoding="utf-8"))

        # clean 이미지 URL
        clean_image_path = clean_dir / f"{type_name}.png"
        if not clean_image_path.is_file():
            print(f"[LAYOUT WARN] cleaned image not found for type={type_name}, path={clean_image_path}, skip.")
            continue

        background_image_url = (
            f"{static_base_url}/{run_id}/clean/{clean_image_path.name}"
        )

        item: Dict[str, Any] = {}

        # ✔ 기존 id 제거 → index 기반으로 front가 씀
        # item["id"] = next_id  (삭제됨)

        item["type"] = type_name
        item["category"] = meta.get("pro_name", template.get("category", ""))

        item["backgroundImageUrl"] = background_image_url

        # canvasData 구성
        canvas = template.get("canvasData", {})
        objects = canvas.get("objects", [])

        for obj in objects:
            role = obj.get("role")
            if not role:
                continue

            key = role.replace("*", "")
            if key in meta:
                obj["text"] = meta[key]

        item["canvasData"] = canvas

        items.append(item)

    # total.json 저장
    total_path = layout_dir / "total.json"
    total_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[LAYOUT] total.json saved to: {total_path}")

    return str(total_path.resolve())


if __name__ == "__main__":
    TEST_RUN_ID = 5
    build_total_layout(TEST_RUN_ID)
