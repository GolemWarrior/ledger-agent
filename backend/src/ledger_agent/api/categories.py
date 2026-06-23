import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from ledger_agent.db.models import Category, Transaction, VendorMemory

logger = logging.getLogger(__name__)
categories_router = APIRouter()


@categories_router.get("/categories")
async def list_categories(request: Request):
    async with request.app.state.async_session_factory() as session:
        stmt = (
            select(Category, func.count(Transaction.id).label("transaction_count"))
            .outerjoin(Transaction, Transaction.category_id == Category.id)
            .group_by(Category.id)
            .order_by(Category.name)
        )
        rows = (await session.execute(stmt)).all()
        data = [
            {"id": cat.id, "name": cat.name, "hint": cat.hint, "transaction_count": count}
            for cat, count in rows
        ]
    return {"data": data, "total": len(data)}


@categories_router.post("/categories", status_code=201)
async def create_category(request: Request):
    body = await request.json()
    name = (body.get("name") or "").strip()
    hint = (body.get("hint") or "").strip() or None
    if not name:
        return JSONResponse(status_code=400, content={"error": "bad_input", "detail": "name is required"})
    async with request.app.state.async_session_factory() as session:
        try:
            cat = Category(name=name, hint=hint)
            session.add(cat)
            await session.commit()
            await session.refresh(cat)
        except IntegrityError:
            await session.rollback()
            return JSONResponse(status_code=409, content={"error": "duplicate_name", "detail": f"Category '{name}' already exists"})
    return JSONResponse(status_code=201, content={"data": {"id": cat.id, "name": cat.name, "hint": cat.hint, "transaction_count": 0}})


@categories_router.patch("/categories/{category_id}")
async def rename_category(category_id: int, request: Request):
    body = await request.json()
    new_name = (body.get("name") or "").strip()
    if not new_name:
        return JSONResponse(status_code=400, content={"error": "bad_input", "detail": "name is required"})
    async with request.app.state.async_session_factory() as session:
        cat = await session.scalar(select(Category).where(Category.id == category_id))
        if cat is None:
            return JSONResponse(status_code=404, content={"error": "not_found", "detail": "Category not found"})
        if cat.name == "Uncategorized":
            return JSONResponse(status_code=400, content={"error": "cannot_rename_uncategorized", "detail": "The Uncategorized category cannot be renamed"})
        cat.name = new_name
        try:
            await session.commit()
            await session.refresh(cat)
        except IntegrityError:
            await session.rollback()
            return JSONResponse(status_code=409, content={"error": "duplicate_name", "detail": f"Category '{new_name}' already exists"})
    return {"data": {"id": cat.id, "name": cat.name, "hint": cat.hint}}


@categories_router.delete("/categories/{category_id}")
async def delete_category(category_id: int, request: Request):
    async with request.app.state.async_session_factory() as session:
        cat = await session.scalar(select(Category).where(Category.id == category_id))
        if cat is None:
            return JSONResponse(status_code=404, content={"error": "not_found", "detail": "Category not found"})
        if cat.name == "Uncategorized":
            return JSONResponse(status_code=400, content={"error": "cannot_delete_uncategorized", "detail": "The Uncategorized category cannot be deleted"})
        uncategorized = await session.scalar(select(Category).where(Category.name == "Uncategorized"))
        if uncategorized is None:
            return JSONResponse(status_code=500, content={"error": "internal_error"})
        await session.execute(
            update(Transaction)
            .where(Transaction.category_id == category_id)
            .values(category_id=uncategorized.id)
        )
        await session.execute(
            update(VendorMemory)
            .where(VendorMemory.category_id == category_id)
            .values(category_id=uncategorized.id)
        )
        await session.delete(cat)
        await session.commit()
    return {"data": {"deleted": True}}
