from pathlib import Path
from typing import List, Dict
import pandas as pd
import datetime

def load_festivals(csv_path: str) -> List[Dict]:
    """
    📄 CSV에서 축제 데이터 로드 (현재 CSV 구조 전용)
    ─────────────────────────────────────────────
    CSV 예시:
    연번 | region | 기초자치단체명 | festival_name | 축제 유형 | 시작일 | 종료일
    """

    p = Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(p)
    df.columns = [c.strip().lower() for c in df.columns]  # 소문자 변환

    # === 컬럼 매핑 ===
    rename_map = {
        "기초자치단체명": "city",
        "축제 유형": "type",
        "시작일": "start_date",
        "종료일": "end_date",
        "연번": "no"
    }
    df.rename(columns={k.lower(): v for k, v in rename_map.items()}, inplace=True)

    # === 필수 컬럼 존재 여부 확인 ===
    required = {"festival_name", "region"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")

    # === year 컬럼 자동 생성 (시작일 기준 or 현재년도) ===
    if "start_date" in df.columns:
        try:
            df["year"] = pd.to_datetime(df["start_date"], errors="coerce").dt.year
        except Exception:
            df["year"] = datetime.datetime.now().year
    else:
        df["year"] = datetime.datetime.now().year

    # === 불필요한 결측 제거 ===
    df = df.dropna(subset=["festival_name", "region"])

    return df.to_dict(orient="records")


def filter_festivals_by_region(festivals: List[Dict], region: str, limit: int) -> List[Dict]:
    """입력한 지역(region)에 해당하는 상위 n개 축제 반환"""
    region_filtered = [f for f in festivals if region in str(f.get("region", ""))]
    return region_filtered[:limit]
