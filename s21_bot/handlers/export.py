from __future__ import annotations
import csv
import io
import logging
from aiogram import Router
from aiogram.filters import Command, Filter
from aiogram.types import Message, BufferedInputFile
from ..config import Config
from ..db.models import get_db

logger = logging.getLogger(__name__)
router = Router(name="export")


class IsModeratorInModChat(Filter):
    async def __call__(self, message: Message, config: Config) -> bool:
        if not message.from_user:
            return False
        return (
            message.from_user.id in config.admin_ids
            and message.chat.id == config.moderation_chat_id
        )


@router.message(IsModeratorInModChat(), Command("export"))
async def cmd_export(message: Message) -> None:
    async with get_db() as db:
        async with db.execute("SELECT * FROM users ORDER BY tg_id") as cur:
            users = await cur.fetchall()
            user_cols = [d[0] for d in cur.description]
        async with db.execute("SELECT * FROM applications ORDER BY id") as cur:
            apps = await cur.fetchall()
            app_cols = [d[0] for d in cur.description]

    if not users and not apps:
        await message.reply("📭 База данных пуста.")
        return

    buf = io.StringIO()

    buf.write("=== USERS ===\n")
    writer = csv.writer(buf)
    writer.writerow(user_cols)
    for row in users:
        writer.writerow(list(row))

    buf.write("\n=== APPLICATIONS ===\n")
    writer.writerow(app_cols)
    for row in apps:
        writer.writerow(list(row))

    csv_bytes = buf.getvalue().encode("utf-8-sig")
    file = BufferedInputFile(csv_bytes, filename="s21_export.csv")
    await message.reply_document(
        file,
        caption=f"📊 Экспорт БД: {len(users)} пользователей, {len(apps)} заявок",
    )


@router.message(Command("exportdebug"))
async def cmd_export_debug(message: Message, config: Config) -> None:
    await message.reply(
        f"chat_id: <code>{message.chat.id}</code>\n"
        f"user_id: <code>{message.from_user.id if message.from_user else '?'}</code>\n"
        f"moderation_chat_id: <code>{config.moderation_chat_id}</code>\n"
        f"is_admin: {message.from_user.id in config.admin_ids if message.from_user else False}",
        parse_mode="HTML",
    )
