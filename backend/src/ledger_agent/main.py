import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ledger_agent.api.router import router
from ledger_agent.config import settings
from ledger_agent.db.base import make_async_engine, make_async_session_factory, make_sync_engine, make_sync_session_factory
from ledger_agent.db.seed import seed_default_categories
from ledger_agent.ingestion.plaid_client import make_plaid_client
from ledger_agent.agent.runner import run_classification_agent

app = FastAPI(title="Ledger Agent")

app.include_router(router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # CRITICAL: never leak API keys or stack traces in responses
    return JSONResponse(status_code=500, content={"error": "internal_error"})


@app.on_event("startup")
async def startup() -> None:
    app.state.async_engine = make_async_engine(settings.database_url)
    app.state.async_session_factory = make_async_session_factory(app.state.async_engine)
    app.state.sync_engine = make_sync_engine(settings.database_url_sync)
    app.state.sync_session_factory = make_sync_session_factory(app.state.sync_engine)
    await seed_default_categories(app.state.async_session_factory)
    app.state.plaid_client = make_plaid_client(settings)
    # Resume any in-progress agent runs from before a restart
    threading.Thread(
        target=run_classification_agent,
        args=(app.state.sync_session_factory, None),
        daemon=True,
    ).start()


@app.get("/health")
async def health():
    return {"status": "ok"}
