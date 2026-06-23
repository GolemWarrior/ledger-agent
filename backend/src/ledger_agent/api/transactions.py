import logging

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ledger_agent.db.models import Transaction, TransactionStatus

logger = logging.getLogger(__name__)

transactions_router = APIRouter()


@transactions_router.get("/transactions")
async def list_transactions(request: Request):
    async with request.app.state.async_session_factory() as session:
        txns = (
            await session.scalars(
                select(Transaction)
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
                "status": t.status.value,
                "account_name": t.account.name,
                "category_name": t.category.name if t.category else ("Transfer" if t.status == TransactionStatus.transfer else None),
                "confidence_score": t.confidence_score,
            }
            for t in txns
        ]
    return {"data": data, "total": len(data)}
