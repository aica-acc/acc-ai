from PIL import Image, ImageDraw, ImageFont
from typing import Tuple, Dict, Any, List
from pathlib import Path

from app.domain.cardnews.cardnews_prompt_model import TableData


def load_font(fonts_dir: str, weight: str, size: int) -> ImageFont.FreeTypeFont:
    """
    weight: "regular" / "bold" / "extra"
    fonts_dir: 나눔 글꼴이 들어있는 디렉토리 (ex: .../data/nanum-all_new/나눔 글꼴)
    """
    font_map = {
        "regular": "NanumSquareNeo-bRg.ttf",  # 기본 본문용
        "bold": "NanumSquareNeo-cBd.ttf",     # 제목/강조용
        "extra": "NanumSquareNeo-dEb.ttf",    # 아주 굵은 강조용
    }

    font_name = font_map.get(weight, font_map["regular"])
    font_path = Path(fonts_dir) / font_name

    try:
        return ImageFont.truetype(str(font_path), size)
    except OSError:
        # 폰트 경로가 잘못됐거나 파일이 없을 경우를 대비한 안전장치
        return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """글자 폭 기준 줄바꿈"""
    lines: List[str] = []
    words = text.split(" ")
    current = ""

    for w in words:
        trial = (current + " " + w).strip()
        if font.getlength(trial) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)

    return lines


def draw_text_box(
    image: Image.Image,
    text: str,
    position: Tuple[int, int],
    font_size: int,
    fonts_dir: str,
    font_weight: str = "bold",
    box_color=(0, 0, 0, 160),
    font_color=(255, 255, 255, 255),
    padding: int = 20,
    max_width_ratio: float = 0.8,
) -> None:
    """
    반투명 박스 + 텍스트 (제목/설명용)
    """
    draw = ImageDraw.Draw(image, "RGBA")
    W, H = image.size
    font = load_font(fonts_dir, font_weight, font_size)
    max_width = int(W * max_width_ratio)

    lines = wrap_text(text, font, max_width)
    line_heights = [font.getbbox(line)[3] for line in lines]
    total_height = sum(line_heights) + padding * 2
    box_width = max(font.getlength(line) for line in lines) + padding * 2

    x, y = position
    box = (x, y, x + box_width, y + total_height)
    draw.rectangle(box, fill=box_color)

    y_offset = y + padding
    for line in lines:
        draw.text((x + padding, y_offset), line, font=font, fill=font_color)
        y_offset += font.getbbox(line)[3]


def draw_plain_text(
    image: Image.Image,
    text: str,
    position: Tuple[int, int],
    font_size: int,
    fonts_dir: str,
    font_weight: str = "regular",
    font_color=(255, 255, 255, 255),
) -> None:
    """
    그냥 텍스트만 (부제, 푸터 등)
    """
    draw = ImageDraw.Draw(image, "RGBA")
    font = load_font(fonts_dir, font_weight, font_size)
    draw.text(position, text, font=font, fill=font_color)


def draw_simple_table(
    image: Image.Image,
    table: TableData,
    position: Tuple[int, int],
    col_widths: List[int],
    fonts_dir: str,
    row_height: int = 60,
    header_fill=(0, 0, 0, 180),
    cell_fill=(0, 0, 0, 120),
    border_color=(255, 255, 255, 180),
    font_size: int = 32,
    padding: int = 10,
) -> None:
    """
    아주 간단한 테이블 렌더링:
    - headers: 상단 헤더
    - rows: 아래 데이터
    - col_widths: 각 column 폭 (px)
    """
    draw = ImageDraw.Draw(image, "RGBA")
    font = load_font(fonts_dir, "regular", font_size)

    x0, y0 = position

    # 헤더 영역
    x = x0
    for i, header in enumerate(table.headers):
        w = col_widths[i]
        cell_box = (x, y0, x + w, y0 + row_height)
        draw.rectangle(cell_box, fill=header_fill, outline=border_color, width=2)

        tw = font.getlength(header)
        th = font.getbbox(header)[3]
        tx = x + (w - tw) / 2
        ty = y0 + (row_height - th) / 2
        draw.text((tx, ty), header, font=font, fill=(255, 255, 255, 255))

        x += w

    # 데이터 행
    y = y0 + row_height
    for row in table.rows:
        x = x0
        for i, cell in enumerate(row.cells):
            w = col_widths[i]
            cell_box = (x, y, x + w, y + row_height)
            draw.rectangle(cell_box, fill=cell_fill, outline=border_color, width=1)

            value = cell.value
            tw = font.getlength(value)
            th = font.getbbox(value)[3]
            tx = x + (w - tw) / 2
            ty = y + (row_height - th) / 2
            draw.text((tx, ty), value, font=font, fill=(255, 255, 255, 255))

            x += w
        y += row_height


def compose_cardnews(
    background_path: str,
    output_path: str,
    layout_config: Dict[str, Any],
    fonts_dir: str,
) -> str:
    """
    layout_config 예:
    {
      "title": {
        "text": "...",
        "position": [80, 120],
        "font_size": 72,
        "use_box": true
      },
      "subtitle": {
        "text": "...",
        "position": [80, 260],
        "font_size": 42,
        "use_box": false
      },
      "description": {
        "text": "...",
        "position": [80, 350],
        "font_size": 38,
        "use_box": true
      },
      "table": {
        "table": TableData(...),
        "position": [80, 600],
        "col_widths": [260, 520]
      },
      "footer": {
        "text": "...",
        "position": [80, 980],
        "font_size": 32,
        "use_box": false
      }
    }
    """

    image = Image.open(background_path).convert("RGBA")

    # 제목
    if "title" in layout_config:
        t = layout_config["title"]
        if t.get("use_box", False):
            draw_text_box(
                image,
                t["text"],
                tuple(t["position"]),
                font_size=t.get("font_size", 60),
                fonts_dir=fonts_dir,
                font_weight="bold",
            )
        else:
            draw_plain_text(
                image,
                t["text"],
                tuple(t["position"]),
                font_size=t.get("font_size", 60),
                fonts_dir=fonts_dir,
                font_weight="bold",
            )

    # 부제목
    if "subtitle" in layout_config:
        s = layout_config["subtitle"]
        if s.get("use_box", False):
            draw_text_box(
                image,
                s["text"],
                tuple(s["position"]),
                font_size=s.get("font_size", 40),
                fonts_dir=fonts_dir,
                font_weight="regular",
            )
        else:
            draw_plain_text(
                image,
                s["text"],
                tuple(s["position"]),
                font_size=s.get("font_size", 40),
                fonts_dir=fonts_dir,
                font_weight="regular",
            )

    # 설명(본문)
    if "description" in layout_config:
        d = layout_config["description"]
        if d.get("use_box", True):
            draw_text_box(
                image,
                d["text"],
                tuple(d["position"]),
                font_size=d.get("font_size", 36),
                fonts_dir=fonts_dir,
                font_weight="regular",
            )
        else:
            draw_plain_text(
                image,
                d["text"],
                tuple(d["position"]),
                font_size=d.get("font_size", 36),
                fonts_dir=fonts_dir,
                font_weight="regular",
            )

    # 표
    if "table" in layout_config:
        tbl_block = layout_config["table"]
        draw_simple_table(
            image,
            table=tbl_block["table"],
            position=tuple(tbl_block["position"]),
            col_widths=tbl_block["col_widths"],
            fonts_dir=fonts_dir,
        )

    # 푸터
    if "footer" in layout_config:
        f = layout_config["footer"]
        if f.get("use_box", False):
            draw_text_box(
                image,
                f["text"],
                tuple(f["position"]),
                font_size=f.get("font_size", 32),
                fonts_dir=fonts_dir,
                font_weight="regular",
            )
        else:
            draw_plain_text(
                image,
                f["text"],
                tuple(f["position"]),
                font_size=f.get("font_size", 32),
                fonts_dir=fonts_dir,
                font_weight="regular",
            )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path