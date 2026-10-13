from __future__ import annotations
import asyncio
import csv
import io
import logging
from aiogram import Router
from aiogram.filters import Command, Filter
from aiogram.types import Message, BufferedInputFile
from ..config import Config
from ..db import UserRepo, ApplicationRepo
from .admin_common import IsModeratorInModChat

logger = logging.getLogger(__name__)
router = Router(name="export")


def _serialize_csv(users: list, user_cols: list[str], apps: list, app_cols: list[str]) -> bytes:
    buf = io.StringIO()

    buf.write("=== USERS ===\n")
    writer = csv.writer(buf)
    writer.writerow(user_cols)
    for row in users:
        writer.writerow(list(row))

    buf.write("\n=== APPLICATIONS ===\n")
    writer = csv.writer(buf)
    writer.writerow(app_cols)
    for row in apps:
        writer.writerow(list(row))

    return buf.getvalue().encode("utf-8-sig")


@router.message(IsModeratorInModChat(), Command("export"))
async def cmd_export(message: Message) -> None:
    user_cols, users = await UserRepo.get_all_for_export()
    app_cols, apps = await ApplicationRepo.get_all_for_export()

    if not users and not apps:
        await message.reply("База данных пуста.")
        return

    csv_bytes = await asyncio.to_thread(_serialize_csv, users, user_cols, apps, app_cols)
    file = BufferedInputFile(csv_bytes, filename="s21_export.csv")
    await message.reply_document(
        file,
        caption=f"Экспорт БД: {len(users)} пользователей, {len(apps)} заявок",
    )


@router.message(IsModeratorInModChat(), Command("exportdebug"))
async def cmd_export_debug(message: Message, config: Config) -> None:
    await message.reply(
        f"chat_id: <code>{message.chat.id}</code>\n"
        f"user_id: <code>{message.from_user.id if message.from_user else '?'}</code>\n"
        f"moderation_chat_id: <code>{config.moderation_chat_id}</code>\n"
        f"is_admin: {message.from_user.id in config.admin_ids if message.from_user else False}",
        parse_mode="HTML",
    )
