# syntax=docker/dockerfile:1
# Python 3.11 (.python-version) / 의존성은 uv.lock 에 고정된 버전 그대로 설치
# torch 는 CPU 전용 빌드 (pyproject.toml 의 pytorch-cpu 인덱스). GPU 라이브러리는 이미지에 들어가지 않는다.
FROM python:3.11.14-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

FROM python:3.11.14-slim-bookworm
# ffmpeg: 영상 이어붙이기 / libcairo2: SVG 변환(cairosvg) / libglib2.0-0, libgomp1: opencv-headless, torch
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libglib2.0-0 libgomp1 libcairo2 fontconfig curl \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY app ./app
# main.py 가 시작 시점에 static 디렉터리를 마운트하므로 반드시 존재해야 한다 (실제 데이터는 compose 볼륨으로 덮어씀)
RUN mkdir -p app/data/total_trend_images app/data/editor app/fonts
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PROJECT_ROOT=/app
EXPOSE 5000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
