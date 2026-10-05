"""Phase 0 bootstrap; domain routes belong to later phases."""

from fastapi import FastAPI

app = FastAPI(title="F1 Intelligence Platform API", version="0.0.0")


@app.get("/")
def index() -> dict[str, str]:
    return {"service": "f1-platform-api", "status": "bootstrap"}
