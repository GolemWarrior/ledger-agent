from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ledger_agent.db.models import Category, VendorMemory

vendor_memory_router = APIRouter()


@vendor_memory_router.get("/vendor-memory")
async def list_vendor_memory(request: Request):
    async with request.app.state.async_session_factory() as session:
        stmt = (
            select(VendorMemory)
            .options(selectinload(VendorMemory.category))
            .order_by(VendorMemory.vendor)
        )
        rows = (await session.scalars(stmt)).all()
        data = [
            {
                "id": vm.id,
                "vendor": vm.vendor,
                "category_id": vm.category_id,
                "category_name": vm.category.name,
                "hit_count": vm.hit_count,
                "last_used_at": vm.last_used_at.isoformat(),
            }
            for vm in rows
        ]
    return {"data": data, "total": len(data)}


@vendor_memory_router.patch("/vendor-memory/{vm_id}")
async def reassign_vendor_memory(vm_id: int, request: Request):
    body = await request.json()
    category_id = body.get("category_id")
    if category_id is None:
        return JSONResponse(status_code=400, content={"error": "bad_input", "detail": "category_id is required"})
    async with request.app.state.async_session_factory() as session:
        vm = await session.scalar(select(VendorMemory).where(VendorMemory.id == vm_id))
        if vm is None:
            return JSONResponse(status_code=404, content={"error": "not_found", "detail": "Vendor memory entry not found"})
        cat = await session.scalar(select(Category).where(Category.id == category_id))
        if cat is None:
            return JSONResponse(status_code=404, content={"error": "not_found", "detail": "Category not found"})
        vm.category_id = category_id
        await session.commit()
        await session.refresh(vm)
    return {"data": {
        "id": vm.id,
        "vendor": vm.vendor,
        "category_id": vm.category_id,
        "category_name": cat.name,
        "hit_count": vm.hit_count,
        "last_used_at": vm.last_used_at.isoformat(),
    }}


@vendor_memory_router.delete("/vendor-memory/{vm_id}")
async def delete_vendor_memory(vm_id: int, request: Request):
    async with request.app.state.async_session_factory() as session:
        vm = await session.scalar(select(VendorMemory).where(VendorMemory.id == vm_id))
        if vm is None:
            return JSONResponse(status_code=404, content={"error": "not_found", "detail": "Vendor memory entry not found"})
        await session.delete(vm)
        await session.commit()
    return {"data": {"deleted": True}}
