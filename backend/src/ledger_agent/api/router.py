from fastapi import APIRouter

# Sub-routers for each resource are mounted here as stories are implemented.
# All routes are prefixed /api/v1/
router = APIRouter(prefix="/api/v1")
