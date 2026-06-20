from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


# --- Async engine + session factory (FastAPI route handlers) ---
# NEVER use AsyncSession inside the LangGraph background thread.
def make_async_engine(database_url: str):
    return create_async_engine(database_url, echo=False)


def make_async_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


# --- Sync engine + session factory (LangGraph background thread) ---
# NEVER share this pool with the async engine above.
def make_sync_engine(database_url: str):
    return create_engine(database_url, echo=False)


def make_sync_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(engine)
