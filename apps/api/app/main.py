"""Application entry point; migrations run separately from API startup."""

from fastapi import FastAPI

from app.api.router import router

app = FastAPI(title="F1 Intelligence Platform API", version="0.0.0")
app.include_router(router)


@app.get("/")
def index() -> dict[str, str]:
    return {"service": "f1-platform-api", "status": "bootstrap"}
