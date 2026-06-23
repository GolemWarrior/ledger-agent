import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

logger = logging.getLogger(__name__)

from ledger_agent.db.models import Account
from ledger_agent.ingestion.plaid_client import (
    create_link_token,
    exchange_public_token,
    fetch_accounts,
)

accounts_router = APIRouter()


@accounts_router.get("/plaid/link-token")
async def get_link_token(request: Request):
    try:
        token = create_link_token(request.app.state.plaid_client)
    except Exception:
        logger.exception("Plaid link token creation failed")
        raise HTTPException(status_code=500, detail="Failed to create link token")
    return {"data": {"link_token": token}}


@accounts_router.post("/plaid/exchange-token")
async def exchange_token(body: dict, request: Request):
    public_token = body.get("public_token")
    if not public_token:
        raise HTTPException(status_code=400, detail="public_token required")

    try:
        access_token, item_id = exchange_public_token(
            request.app.state.plaid_client, public_token
        )
    except Exception:
        logger.exception("Plaid public token exchange failed")
        raise HTTPException(status_code=500, detail="Plaid exchange failed")

    try:
        plaid_accounts = fetch_accounts(request.app.state.plaid_client, access_token)
    except Exception:
        logger.exception("Plaid accounts fetch failed after successful token exchange")
        raise HTTPException(status_code=500, detail="Plaid exchange failed")

    async with request.app.state.async_session_factory() as session:
        created = []
        for acct in plaid_accounts:
            existing = await session.scalar(
                select(Account).where(Account.plaid_account_id == acct["plaid_account_id"])
            )
            if existing is None:
                new_acct = Account(
                    plaid_account_id=acct["plaid_account_id"],
                    name=acct["name"],
                    type=acct["type"],
                    access_token=access_token,
                    item_id=item_id,
                    last_synced_at=None,
                )
                session.add(new_acct)
                created.append(new_acct)
        await session.commit()
        for acct in created:
            await session.refresh(acct)

        all_accounts = (await session.scalars(select(Account))).all()

    return {
        "data": [
            {
                "id": a.id,
                "plaid_account_id": a.plaid_account_id,
                "name": a.name,
                "type": a.type,
                "last_synced_at": a.last_synced_at,
            }
            for a in all_accounts
        ],
        "total": len(all_accounts),
    }


@accounts_router.get("/accounts")
async def list_accounts(request: Request):
    async with request.app.state.async_session_factory() as session:
        accounts = (await session.scalars(select(Account))).all()
    return {
        "data": [
            {
                "id": a.id,
                "plaid_account_id": a.plaid_account_id,
                "name": a.name,
                "type": a.type,
                "last_synced_at": a.last_synced_at,
            }
            for a in accounts
        ],
        "total": len(accounts),
    }
