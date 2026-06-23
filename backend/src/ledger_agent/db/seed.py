from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ledger_agent.db.models import Category

DEFAULT_CATEGORIES = [
    "Groceries", "Dining", "Transportation", "Utilities", "Housing",
    "Healthcare", "Entertainment", "Shopping", "Transfer", "Uncategorized",
]


async def seed_default_categories(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(Category))
        if count == 0:
            session.add_all([Category(name=name) for name in DEFAULT_CATEGORIES])
            await session.commit()
