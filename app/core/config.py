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

# 응답에 넣는 정적 파일(/static/...) URL 의 공개 주소.
# 브라우저는 AI 서버에 직접 접근하지 않고 백엔드(/static/** 중계)를 거치므로 백엔드 주소가 기본값이다.
AI_PUBLIC_BASE_URL = os.getenv("AI_PUBLIC_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
STATIC_BASE_URL = os.getenv("STATIC_BASE_URL", f"{AI_PUBLIC_BASE_URL}/static/editor")
TREND_IMAGE_BASE_URL = f"{AI_PUBLIC_BASE_URL}/static/total_trend_images"

# OpenAI 텍스트 모델 (기획서 분석, 포스터 스타일 제안, 리포트).
# gpt-4-turbo / gpt-3.5-turbo 는 OpenAI 에서 지원 종료되어 호출 시 404. 환경변수로 바꿀 수 있다.
OPENAI_TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")

# 에디터 준비 단계의 '이미지 속 글자 지우기'. CLIPDROP_API_KEY 가 있으면 항상 ClipDrop 이 우선이다.
#  - openai    : OPENAI_API_KEY 로 이미지 편집 (기본 gpt-image-2.5-flare). 실측에서 글자 외 요소를 가장 잘 유지하고
#                원본 비율·높은 해상도로 돌려주며 장당 약 $0.02 (2026-10 비교, docs/TROUBLESHOOTING.md #20)
#  - replicate : REPLICATE_API_TOKEN 으로 google/nano-banana. 글자가 없으면 장식 요소를 지우는 경향
#  - gemini    : GEMINI_API_KEY 로 구글에 직접. 무료 등급 키는 이미지 모델 한도가 없어 결제 연결 필요
# openai·gemini 가 실패하면 Replicate 로 대체한다
TEXT_REMOVAL_PROVIDER = os.getenv("TEXT_REMOVAL_PROVIDER", "openai").lower()
TEXT_REMOVAL_MODEL = os.getenv("TEXT_REMOVAL_MODEL") or {
    "replicate": "google/nano-banana",
    "gemini": "gemini-2.5-flash-image",
}.get(TEXT_REMOVAL_PROVIDER, "gpt-image-2.5-flare")
