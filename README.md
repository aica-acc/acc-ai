# acc-ai

ACC(축제 홍보물 자동생성 서비스)의 **AI 서버**입니다. FastAPI 로 만들어졌고,
기획서·트렌드 분석, 프롬프트 생성, 이미지·영상 생성, OCR/에디터 후처리를 담당합니다.
이 서버는 **백엔드(`acc-backend`)만 호출**합니다. 브라우저는 AI 서버에 직접 접근하지 않습니다.

```
브라우저 ──▶ acc-front(nginx) ──/api/, /static/──▶ acc-backend (Spring :8081) ──▶ acc-ai (FastAPI :5000)
생성된 파일은 공유 폴더(app/data, promotion, front public)에 저장
```

정적 파일(`/static/...`)도 백엔드가 중계합니다(`AiStaticProxyController`). 그래서 응답에 넣는 이미지 URL은 백엔드 또는 사이트 주소(`AI_PUBLIC_BASE_URL`)를 기준으로 만듭니다.

## 주요 기능

| 영역 | 설명 |
|---|---|
| 기획서 분석 | PDF/Word/HWP 기획서에서 축제명·기간·장소·콘셉트 등 메타데이터 추출 (`/analyze/proposal`) |
| 트렌드 분석 | 키워드·지역 트렌드 (네이버 데이터랩, YouTube, SerpAPI 크롤링) (`/analyze/total_trend`, `/region_trend`) |
| 프롬프트 · 이미지 생성 | LangChain / LangGraph + OpenAI·Replicate·Gemini 로 포스터·마스코트 생성 (`/generate-prompt`, `/create-image`) |
| 파생 홍보물 | 현수막·버스/지하철 광고·카드뉴스·리플렛·굿즈·표지판·로고 생성 |
| 영상 | 포스터/마스코트/축제 홍보영상 (Gemini Veo, ffmpeg, moviepy) |
| 에디터 | 레이아웃 템플릿 생성, 텍스트 OCR(PaddleOCR), AI 색상·폰트 추천 (`/editor/*`) |
| 리포트 | 보도자료·공지·SNS 글·패키지 생성 (`/report/*`) |

API 문서는 서버를 띄운 뒤 **`http://localhost:5000/docs`** (Swagger) 에서 볼 수 있습니다.

## 기술 스택

- Python **3.11** (`.python-version`), 패키지 관리 **uv** (`uv.lock` 으로 버전 고정)
- FastAPI, Uvicorn
- LangChain, LangGraph, OpenAI, Replicate, Google GenAI(Gemini)
- PaddleOCR, Ultralytics(YOLO), OpenCV, Pillow, CairoSVG
- moviepy, **ffmpeg**
- ChromaDB, sentence-transformers, transformers (torch)
- Selenium, BeautifulSoup, yt-dlp (수집)

## 빠른 실행 (로컬)

사전 준비: Python 3.11, [uv](https://docs.astral.sh/uv/), **ffmpeg**(PATH 에 등록), 디스크 여유 수 GB
(`torch` 와 CUDA 라이브러리가 `uv.lock` 대로 설치되어 매우 큽니다).

```bash
# 1) 의존성 설치
uv sync

# 2) 환경변수 파일 만들기
cp .env.example .env        # 값을 채운다 (아래 "환경변수" 참고)

# 3) 필요한 데이터 폴더 준비 (아래 "필수 데이터 폴더" 참고)

# 4) 서버 실행 (백엔드가 5000 포트를 기대합니다: python.api.url)
uv run uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload
```

확인: `http://localhost:5000/` → `{"message":"Festival Promotion API is running"}`

> **주의**: `YOUTUBE_API_KEY` 등 일부 키는 **서버가 import 되는 시점에 바로 쓰입니다.** 비어 있으면 기동 중에 종료됩니다.
> 실제 키가 없다면 아무 값이라도 넣어야 서버가 뜹니다. (해당 기능은 동작하지 않습니다.)
> 기동에는 모델 라이브러리를 읽느라 1~2분 걸립니다.

## 환경변수 (`.env`)

`.env.example` 을 복사해서 사용합니다. `.env` 는 `.gitignore` 대상입니다.

| 변수 | 용도 |
|---|---|
| `OPENAI_API_KEY` | LLM / 이미지 분석 |
| `GEMINI_API_KEY` | Gemini / 영상 생성 |
| `REPLICATE_API_TOKEN` | 이미지 생성 (Replicate) |
| `CLIPDROP_API_KEY` | 이미지 텍스트 제거 |
| `YOUTUBE_API_KEY` | YouTube 트렌드 (**기동 시 필요**) |
| `SERPAPI_API_KEY` | 이미지/검색 크롤링 |
| `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | 네이버 데이터랩 트렌드 |
| `PINECONE_API_KEY`, `HUGGING_FACE_TOKEN`, `TAVILY_API_KEY` | 벡터DB / 모델 / 검색 |
| `CLOUDCONVERT_API_KEY` | HWP 기획서를 PDF 로 변환 |
| `PROJECT_ROOT` | 이 레포 루트 경로 (**필수**) |
| `FRONT_PROJECT_ROOT` | `acc-front` 레포 루트 경로 (**필수**). 하위 `public/data/promotion/...` 에 결과물 저장 |
| `FILE_ROOT` | 파일 공유 루트 |
| `DATA_ROOT`, `EDITOR_ROOT_DIR`, `PROMOTION_DIR`, `BANNER_SAVE_DIR` | (선택) 데이터·에디터·생성물·배너 저장 폴더. 비우면 레포 기준 상대 위치 |
| `AI_PUBLIC_BASE_URL` | 응답에 넣는 정적 파일 URL의 공개 주소. 브라우저는 백엔드의 `/static/**` 중계를 거치므로 기본값은 백엔드 주소(`http://127.0.0.1:8081`). 도메인으로 서비스하면 사용자가 접속하는 주소 |
| `STATIC_BASE_URL` | (선택) 에디터 정적 URL. 기본 `AI_PUBLIC_BASE_URL + /static/editor` |

경로 관련 값은 `app/core/config.py` 한 곳에서 읽습니다. 코드에서 경로가 필요하면 하드코딩하지 말고 이 모듈을 쓰세요.

## 필수 데이터 폴더

레포에는 용량·저작권 문제로 데이터 파일이 들어 있지 않습니다(`.gitignore`). 아래가 없으면 서버가 시작하지 않거나 일부 기능이 실패합니다.

| 위치 | 내용 |
|---|---|
| `app/data/total_trend_images/` | 트렌드 이미지 (**없으면 서버 시작 실패**, 폴더만 있어도 됨) |
| `app/data/editor/layout_templates/` | 에디터 레이아웃 JSON (`layout_templates.zip` 을 `app/data/editor/` 에 풀기) |
| `app/data/nanum-all_new/` | 나눔 폰트 |
| `app/data/report/` | 리포트용 데이터 |
| `app/fonts/Jalnan2TTF.ttf` | 인트로 자막용 한글 폰트 (**없으면 서버 기동 실패**) |
| `<FRONT_PROJECT_ROOT>/public/data/promotion/M000001/25/poster/` | few-shot 이미지 (`card.png`, `good_2.jpg`) |

## API 개요

라우터 접두어별 정리입니다. 자세한 요청/응답은 `/docs` 를 보세요.

| 접두어 | 설명 |
|---|---|
| `/analyze/*` | 기획서·키워드 트렌드·지역 트렌드 분석 |
| (루트) `/generate-prompt`, `/create-image`, `/create-mascot-image`, `/generate/mascot/prompt` | 프롬프트·이미지 생성 |
| `/poster/*` | 포스터 생성 / 확정 |
| `/banner/*` | 배너·현수막 |
| `/editor/*` | 에디터 템플릿 빌드(`/build`), 렌더(`/render`), 색상 추천 |
| `/festival/*` | 축제 정보 |
| `/report/*` | 기사·공지·SNS·패키지 리포트 |
| `/static/*` | `app/data` 정적 파일 서빙 (생성 이미지 등). 브라우저에는 백엔드가 중계 |

## Docker

`Dockerfile` 은 멀티 스테이지입니다.

- 빌더: `uv sync --frozen` 으로 `uv.lock` 그대로 설치.
  `openai/CLIP` 은 최신 setuptools 에서 `pkg_resources` 가 없어 빌드가 깨지므로, `clip` 만 따로 `setuptools<81` 환경에서 격리 없이 설치합니다.
- 런타임: `python:3.11-slim` + `ffmpeg`, `libgl1`, `libcairo2` 등.
- 데이터 폴더(`app/data`, `app/fonts`)는 이미지에 넣지 않고 **볼륨으로 마운트**합니다.
- 이미지 크기는 약 **4.8GB(압축)** / 15.8GB(풀었을 때) 입니다. 첫 빌드에 시간이 오래 걸립니다.

```bash
docker build -t scv3114/acc-ai .
docker run -p 5000:5000 --env-file .env \
  -e PROJECT_ROOT=/app -e FRONT_PROJECT_ROOT=/data/acc-front -e FILE_ROOT=/data/acc \
  -v $(pwd)/app/data:/app/app/data -v $(pwd)/app/fonts:/app/app/fonts:ro \
  scv3114/acc-ai
```

도커 허브 이미지는 `scv3114/acc-ai` 입니다. 전체 서비스를 한 번에 띄우는 방법은 배포용 폴더의 `docker-compose.yml` / README 를 참고하세요.

## 폴더 구조

```
app/
├─ main.py          FastAPI 앱, 라우터 등록, /static 마운트
├─ core/config.py   경로·서버 주소 공용 설정 (환경변수 → 상대경로 기본값)
├─ api/             라우터 (routes_*.py)
├─ service/         기능별 로직 (poster, banner, bus, subway, goods, sign, logo, cardnews, leaflet, video, editor, report, total_trend ...)
├─ domain/          요청/응답 모델
├─ tools/           기획서 파싱, 카드뉴스/배너 도구
├─ poster_service/  포스터 수집·점수화 하베스터
└─ data/, fonts/    런타임 데이터 (git 제외)
```

## 개발 팁

- 각 `service/*` 파일 아래쪽의 `if __name__ == "__main__":` 블록으로 단독 실행해 볼 수 있습니다. 데모 경로는 `app/data/...` 기준 상대경로입니다.
- 새 경로가 필요하면 `app/core/config.py` 에 추가하고 환경변수로 덮어쓸 수 있게 하세요.
- `.gitignore` 에 `*.json`, `*.csv`, `*.png`, `*.pdf`, `*.mp4`, `*.txt`, `*.ttf` 가 들어 있어 데이터 파일이 실수로 올라가지 않습니다. 반대로 이런 확장자의 코드/설정 파일은 `git add -f` 가 필요합니다.
