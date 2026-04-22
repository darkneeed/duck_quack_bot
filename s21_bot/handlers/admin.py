from aiogram import Router

from .admin_callbacks import router as admin_callbacks_router
from .admin_posts import router as admin_posts_router
from .admin_users import router as admin_users_router

router = Router(name="admin")
router.include_router(admin_callbacks_router)
router.include_router(admin_posts_router)
router.include_router(admin_users_router)

__all__ = ["router"]
