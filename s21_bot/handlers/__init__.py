from aiogram import Router
from .user import router as user_router
from .moderation import router as moderation_router
from .admin import router as admin_router
from .community import router as community_router
from .profile import router as profile_router
from .export import router as export_router
from .verification import router as verification_router
from .invite_code import router as invite_code_router
from .where import router as where_router
from .chat_moderation import router as chat_moderation_router


def setup_routers() -> Router:
    root = Router(name="root")
    root.include_router(invite_code_router)
    root.include_router(verification_router)
    root.include_router(admin_router)
    root.include_router(export_router)
    root.include_router(moderation_router)
    root.include_router(community_router)
    root.include_router(profile_router)
    root.include_router(where_router)
    root.include_router(chat_moderation_router)
    root.include_router(user_router)
    return root


__all__ = ["setup_routers"]
