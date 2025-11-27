from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes_festival, routes_images, routes_poster, routes_proposal, routes_total_trend
from fastapi.staticfiles import StaticFiles
from app.api import routes_liveposter
from app.api import routes_region_trend
import os

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
app.include_router(routes_images.router)
app.include_router(routes_poster.router)
app.include_router(routes_proposal.router)
app.include_router(routes_total_trend.router)
app.include_router(routes_liveposter.router)
app.include_router(routes_region_trend.router)

@app.get("/")
def root():
    return {"message": "Festival Promotion API is running"}

