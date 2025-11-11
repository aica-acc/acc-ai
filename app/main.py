# from fastapi import FastAPI
# from app.api import routes_festival
# from app.api import routes_images

# app = FastAPI(title="Festival Analyzer API")

# app.include_router(routes_festival.router)
# app.include_router(routes_images.router)

# @app.get("/")
# def root():
#     return {"message": "Festival Analyzer API is running"}

###################### 임 시 ############################
# app/main.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("uvicorn.error")

def create_app() -> FastAPI:
    app = FastAPI(title="ACC AI API", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"ok": True}

    # 배너 라우터만 필수 로드
    try:
        from app.api.routes_banner import router as banner_router
        app.include_router(banner_router)
        logger.info("Loaded routes: /banner/*")
    except Exception as e:
        logger.exception("Failed to load banner routes: %s", e)

    # 선택 라우터들(문제 있어도 서버는 떠야 함)
    try:
        from app.api.routes_images import router as images_router
        app.include_router(images_router)
    except Exception as e:
        logger.warning("Images routes not loaded: %s", e)

    try:
        from app.api.routes_festival import router as festival_router
        app.include_router(festival_router)
    except Exception as e:
        logger.warning("Festival routes not loaded: %s", e)

    return app

app = create_app()
