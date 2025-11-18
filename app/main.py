from dotenv import load_dotenv
from pathlib import Path
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes_cardnews_images, routes_festival, routes_poster

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")
app = FastAPI(title="Festival Promotion API")

app.include_router(routes_festival.router)
app.include_router(routes_cardnews_images.router)
app.include_router(routes_poster.router)

@app.get("/")
def root():
    return {"message": "Festival Promotion API is running"}
