from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes_festival, routes_images, routes_poster, routes_banner, routes_proposal
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Festival Promotion API")

app.include_router(routes_festival.router)
app.include_router(routes_images.router)
app.include_router(routes_poster.router)
app.include_router(routes_banner.router)
app.include_router(routes_proposal.router)
# app.include_router(routes_total_trend.router)

# app/api/data 폴더를 /static 이라는 URL로 매핑
app.mount(
    "/static",
    StaticFiles(directory="app/data"),
    name="static",
)


@app.get("/")
def root():
    return {"message": "Festival Promotion API is running"}
