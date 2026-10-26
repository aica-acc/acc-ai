"""경로 / 서버 주소 공용 설정.

모든 값은 환경변수(.env)로 덮어쓸 수 있고, 없으면 레포 내부 상대 위치를 기본값으로 쓴다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parents[1]          # <repo>/app
REPO_DIR = APP_DIR.parent                              # <repo>
load_dotenv(REPO_DIR / ".env")

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT") or REPO_DIR).resolve()
DATA_ROOT = Path(os.getenv("DATA_ROOT") or APP_DIR / "data").resolve()
EDITOR_ROOT_DIR = Path(os.getenv("EDITOR_ROOT_DIR") or DATA_ROOT / "editor").resolve()
PROMOTION_DIR = Path(os.getenv("PROMOTION_DIR") or PROJECT_ROOT / "promotion").resolve()
BANNER_SAVE_DIR = Path(os.getenv("BANNER_SAVE_DIR") or DATA_ROOT / "banners").resolve()

# 브라우저/백엔드가 AI 서버의 정적 파일에 접근할 때 쓰는 주소
AI_PUBLIC_BASE_URL = os.getenv("AI_PUBLIC_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
STATIC_BASE_URL = os.getenv("STATIC_BASE_URL", f"{AI_PUBLIC_BASE_URL}/static/editor")
TREND_IMAGE_BASE_URL = f"{AI_PUBLIC_BASE_URL}/static/total_trend_images"
