from fastapi import APIRouter
from pathlib import Path
import requests

from app.service.cardnews.replicate_image_generator import generate_image_from_prompt
from app.service.cardnews.text_overlay_service import compose_cardnews
from app.domain.cardnews.cardnews_prompt_model import TableData, TableRow, TableCell

router = APIRouter()

@router.post("/generate-full")
def generate_full_cardnews(payload: dict):
    """
    유저가 승인한 visual_prompt + 텍스트/표를 받아서
    1) Replicate로 배경 생성
    2) 텍스트/표 오버레이
    3) 최종 카드뉴스 이미지 파일 경로 반환
    """

    visual_prompt: str = payload["visual_prompt"]   # 유저가 최종 승인한 프롬프트
    title: str = payload["title"]
    subtitle: str | None = payload.get("subtitle")
    description: str | None = payload.get("description")
    footer_text: str | None = payload.get("footer_text")
    table_payload = payload.get("table")  # { "headers": [...], "rows": [[...], ...] } 형태 기대

    # 1) Replicate로 배경 이미지 생성 (URL)
    bg_url = generate_image_from_prompt(visual_prompt)

    # 2) 배경 이미지를 로컬에 다운로드
    base_dir = Path("output") / "cardnews"
    base_dir.mkdir(parents=True, exist_ok=True)

    bg_path = base_dir / "background.png"
    resp = requests.get(bg_url)
    resp.raise_for_status()
    bg_path.write_bytes(resp.content)

    # 3) 레이아웃 설정 (기본 템플릿)
    layout_config: dict = {
        "title": {
            "text": title,
            "position": [80, 120],
            "font_size": 70,
            "use_box": True,
        }
    }

    if subtitle:
        layout_config["subtitle"] = {
            "text": subtitle,
            "position": [80, 260],
            "font_size": 42,
            "use_box": False,
        }

    if description:
        layout_config["description"] = {
            "text": description,
            "position": [80, 350],
            "font_size": 36,
            "use_box": True,
        }

    # 4) 표 데이터가 있다면 TableData로 변환 후 오버레이 설정
    if table_payload:
        headers = table_payload.get("headers", [])
        rows_raw = table_payload.get("rows", [])

        table_rows: list[TableRow] = []
        for row in rows_raw:
            cells = [TableCell(value=str(v)) for v in row]
            table_rows.append(TableRow(cells=cells))

        table_data = TableData(headers=headers, rows=table_rows)

        layout_config["table"] = {
            "table": table_data,
            "position": [80, 600],
            "col_widths": [260, 520],  # 2컬럼 기준 예시
        }

    if footer_text:
        layout_config["footer"] = {
            "text": footer_text,
            "position": [80, 980],
            "font_size": 30,
            "use_box": False,
        }

    # 5) 최종 카드뉴스 합성
    final_path = base_dir / "cardnews_final.png"
    compose_cardnews(
        background_path=str(bg_path),
        output_path=str(final_path),
        layout_config=layout_config,
    )

    return {
        "result_path": str(final_path),
        "background_url": bg_url,
    }