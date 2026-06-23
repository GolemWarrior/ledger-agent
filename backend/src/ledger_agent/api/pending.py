import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ledger_agent.db.models import Transaction, TransactionStatus

logger = logging.getLogger(__name__)

pending_router = APIRouter()


class ResolveRequest(BaseModel):
    answer: str


def _resume_graph(sync_session_factory, settings, transaction_id: int, answer: str) -> None:
    """Resume escalated LangGraph run with user's answer. Sync — called via run_in_executor."""
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.types import Command
    from ledger_agent.agent.graph import build_graph

    conn_string = settings.database_url_sync.replace("postgresql+psycopg://", "postgresql://")
    with sync_session_factory() as session:
        with PostgresSaver.from_conn_string(conn_string) as checkpointer:
            compiled = build_graph(session, settings).compile(checkpointer=checkpointer)
            thread_config = {"configurable": {"thread_id": f"txn-{transaction_id}"}}
            compiled.invoke(Command(resume=answer), config=thread_config)


@pending_router.get("/transactions/pending")
async def list_pending(request: Request):
    async with request.app.state.async_session_factory() as session:
        txns = (
            await session.scalars(
                select(Transaction)
                .where(Transaction.status == TransactionStatus.escalated)
                .options(
                    selectinload(Transaction.account),
                    selectinload(Transaction.category),
                )
                .order_by(Transaction.date.desc(), Transaction.id.desc())
            )
        ).all()
        data = [
            {
                "id": t.id,
                "description": t.description,
                "merchant_name": t.merchant_name,
                "amount": str(t.amount),
                "date": t.date.isoformat(),
                "account_name": t.account.name,
                "category_name": t.category.name if t.category else None,
                "escalation_question": t.escalation_question,
            }
            for t in txns
        ]
    return {"data": data, "total": len(data)}


@pending_router.post("/transactions/{transaction_id}/resolve")
async def resolve_transaction(transaction_id: int, body: ResolveRequest, request: Request):
    async with request.app.state.async_session_factory() as session:
        txn = await session.get(Transaction, transaction_id)
        if txn is None:
            return JSONResponse(
                status_code=404,
                content={"error": "not_found", "detail": "Transaction not found"},
            )
        if txn.status != TransactionStatus.escalated:
            return JSONResponse(
                status_code=400,
                content={"error": "not_escalated", "detail": "Transaction is not in escalated state"},
            )

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        _resume_graph,
        request.app.state.sync_session_factory,
        request.app.state.settings,
        transaction_id,
        body.answer,
    )

    return {"data": {"transaction_id": transaction_id, "status": "resolved"}}
