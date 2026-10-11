"""Application entry point; migrations run separately from API startup."""

from fastapi import FastAPI
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.router import router
from app.services.auth_body import AccountBodyLimit

app = FastAPI(title="F1 Intelligence Platform API", version="0.0.0")
app.add_middleware(AccountBodyLimit)
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def safe_account_validation(request, error):
    if request.url.path.startswith("/v1/auth/"):
        return JSONResponse(
            status_code=422,
            content={"detail": "Check the sign-in name and password requirements"},
        )
    return await request_validation_exception_handler(request, error)


@app.get("/")
def index() -> dict[str, str]:
    return {"service": "f1-platform-api", "status": "bootstrap"}
