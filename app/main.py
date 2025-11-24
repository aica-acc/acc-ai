from dotenv import load_dotenv
from pathlib import Path
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes_festival, routes_poster, routes_proposal, routes_total_trend, routes_cardnews_images
from fastapi.staticfiles import StaticFiles
import os

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="Festival Promotion API")

TOTAL_TREND_IMAGE_DIR = os.path.join(
    os.getcwd(),
    "app",
    "data",
    "total_trend_images"
)

app.mount(
    "/static/total_trend_images",
    StaticFiles(directory=TOTAL_TREND_IMAGE_DIR),
    name="total_trend_images"
)

app.include_router(routes_festival.router)
app.include_router(routes_cardnews_images.router)
app.include_router(routes_poster.router)
# app.include_router(routes_banner.router)
app.include_router(routes_proposal.router)
app.include_router(routes_total_trend.router)

# app/api/data 폴더를 /static 이라는 URL로 매핑
app.mount(
    "/static",
    StaticFiles(directory="app/data"),
    name="static",
)


@app.get("/")
def root():
    return {"message": "Festival Promotion API is running"}
