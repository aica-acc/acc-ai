from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes_festival, routes_images

app = FastAPI(title="Festival Promotion API")

app.include_router(routes_festival.router)
app.include_router(routes_images.router)

@app.get("/")
def root():
    return {"message": "Festival Promotion API is running"}
