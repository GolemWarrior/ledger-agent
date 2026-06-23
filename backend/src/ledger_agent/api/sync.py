import logging
import threading

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from ledger_agent.db.models import Account, SyncRun, SyncRunStatus
from ledger_agent.ingestion.sync import run_full_sync
from ledger_agent.agent.runner import run_classification_agent

logger = logging.getLogger(__name__)

sync_router = APIRouter()


@sync_router.post("/sync", status_code=202)
async def trigger_sync(request: Request):
    async with request.app.state.async_session_factory() as session:
        active = await session.scalar(
            select(SyncRun).where(SyncRun.status == SyncRunStatus.processing)
        )
        if active:
            raise HTTPException(
                status_code=409,
                detail={"error": "sync_in_progress", "detail": "A sync is already running"},
            )
        sync_run = SyncRun(status=SyncRunStatus.processing, processed=0, total=0)
        session.add(sync_run)
        await session.commit()
        await session.refresh(sync_run)
        sync_run_id = sync_run.id

    def _sync_and_classify(session_factory, plaid_client, sync_run_id):
        run_full_sync(session_factory, plaid_client, sync_run_id)
        run_classification_agent(session_factory, sync_run_id)

    threading.Thread(
        target=_sync_and_classify,
        args=(request.app.state.sync_session_factory, request.app.state.plaid_client, sync_run_id),
        daemon=True,
    ).start()

    return {"data": {"sync_run_id": sync_run_id}}


@sync_router.get("/sync/status")
async def get_sync_status(request: Request):
    async with request.app.state.async_session_factory() as session:
        latest_run = await session.scalar(
            select(SyncRun).order_by(SyncRun.started_at.desc())
        )
        last_synced_at = await session.scalar(select(func.max(Account.last_synced_at)))

    if not latest_run:
        return {"data": {"status": "idle", "processed": 0, "total": 0, "last_synced_at": None, "error": None}}

    return {
        "data": {
            "status": latest_run.status.value,
            "processed": latest_run.processed,
            "total": latest_run.total,
            "last_synced_at": last_synced_at.isoformat() if last_synced_at else None,
            "error": latest_run.error,
        }
    }
