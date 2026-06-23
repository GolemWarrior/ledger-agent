from fastapi import APIRouter

from ledger_agent.api.accounts import accounts_router
from ledger_agent.api.pending import pending_router
from ledger_agent.api.sync import sync_router
from ledger_agent.api.transactions import transactions_router

router = APIRouter(prefix="/api/v1")
router.include_router(accounts_router)
router.include_router(sync_router)
router.include_router(pending_router)
router.include_router(transactions_router)
