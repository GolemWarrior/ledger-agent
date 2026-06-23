import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ledger_agent.db.models import VendorMemory

logger = logging.getLogger(__name__)


def lookup_vendor_memory(session: Session, vendor: str) -> Optional[VendorMemory]:
    """Return VendorMemory entry for the given vendor name, or None if not found."""
    return session.scalar(
        select(VendorMemory)
        .where(VendorMemory.vendor == vendor)
        .options(selectinload(VendorMemory.category))
    )
