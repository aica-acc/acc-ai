from fastapi import FastAPI
from app.api import routes_festival
from app.api import routes_images

app = FastAPI(title="Festival Analyzer API")

app.include_router(routes_festival.router)
app.include_router(routes_images.router)

@app.get("/")
def root():
    return {"message": "Festival Analyzer API is running"}
