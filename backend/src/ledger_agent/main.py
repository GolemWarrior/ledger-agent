from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ledger_agent.api.router import router
from ledger_agent.config import settings
from ledger_agent.db.base import make_async_engine, make_async_session_factory, make_sync_engine, make_sync_session_factory

app = FastAPI(title="Ledger Agent")

app.include_router(router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # CRITICAL: never leak API keys or stack traces in responses
    return JSONResponse(status_code=500, content={"error": "internal_error"})


@app.on_event("startup")
async def startup() -> None:
    # Initialise both engine/session factories so imported modules can use them.
    app.state.async_engine = make_async_engine(settings.database_url)
    app.state.async_session_factory = make_async_session_factory(app.state.async_engine)
    app.state.sync_engine = make_sync_engine(settings.database_url_sync)
    app.state.sync_session_factory = make_sync_session_factory(app.state.sync_engine)


@app.get("/health")
async def health():
    return {"status": "ok"}
