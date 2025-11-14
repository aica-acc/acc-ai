from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes_festival, routes_images, routes_poster, routes_proposal, routes_total_trend

app = FastAPI(title="Festival Promotion API")

app.include_router(routes_festival.router)
app.include_router(routes_images.router)
app.include_router(routes_poster.router)
app.include_router(routes_proposal.router)
# app.include_router(routes_total_trend.router)

@app.get("/")
def root():
    return {"message": "Festival Promotion API is running"}
