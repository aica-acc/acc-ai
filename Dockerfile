# syntax=docker/dockerfile:1
# Python 3.11 (.python-version) / 의존성은 uv.lock 에 고정된 버전 그대로 설치
FROM python:3.11.14-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential \
 && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
# openai/CLIP(git) 의 setup.py 는 pkg_resources 를 import 하는데 최신 setuptools(>=81)에는 없다.
# → clip 만 제외하고 lock 대로 설치한 뒤, setuptools<81 환경에서 격리 없이 clip 을 따로 설치한다.
RUN --mount=type=cache,target=/root/.cache/uv     uv sync --frozen --no-install-project --no-dev --no-install-package clip  && uv pip install --python .venv/bin/python "setuptools<81" wheel  && uv pip install --python .venv/bin/python --no-build-isolation --no-deps       "clip @ git+https://github.com/openai/CLIP.git@dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1"

FROM python:3.11.14-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libgl1 libglib2.0-0 libgomp1 libcairo2 fontconfig curl \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY app ./app
# main.py 가 시작 시점에 static 디렉터리를 마운트하므로 반드시 존재해야 한다 (실제 데이터는 compose 볼륨으로 덮어씀)
RUN mkdir -p app/data/total_trend_images app/data/editor app/fonts
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PROJECT_ROOT=/app
EXPOSE 5000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
