from aiogram import Router

from .auth import router as auth_router
from .cabinet import router as cabinet_router

router = Router(name="user")
router.include_router(cabinet_router)
router.include_router(auth_router)

__all__ = ["router"]
