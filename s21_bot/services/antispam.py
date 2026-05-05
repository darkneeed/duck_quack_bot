from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from aiogram import Bot
from aiogram.types import Message, ChatPermissions

from ..config import Config
from ..db.models import get_db
from ..utils.telegram import send_message_with_topic

logger = logging.getLogger(__name__)


@dataclass
class _SpamState:
    timestamps: deque[float] = field(default_factory=deque)
    warning_until: float = 0.0
    last_event_at: float = 0.0
    seen_media_groups: dict[str, float] = field(default_factory=dict)


_states: dict[tuple[int, int], _SpamState] = defaultdict(_SpamState)


async def init_antispam_table() -> None:
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS antispam_config (
                id            INTEGER PRIMARY KEY CHECK (id = 1),
                enabled       INTEGER NOT NULL DEFAULT 0,
                msg_count     INTEGER NOT NULL DEFAULT 5,
                window_secs   INTEGER NOT NULL DEFAULT 10,
                mute_minutes  INTEGER NOT NULL DEFAULT 30
            )
        """)
        await db.execute(
            "INSERT OR IGNORE INTO antispam_config (id) VALUES (1)"
        )
        await db.commit()


async def get_config() -> dict:
    async with get_db() as db:
        async with db.execute("SELECT * FROM antispam_config WHERE id=1") as cur:
            row = await cur.fetchone()
    if row is None:
        return {"enabled": 0, "msg_count": 5, "window_secs": 10, "mute_minutes": 30}
    return dict(row)


async def set_config(enabled: int, msg_count: int, window_secs: int, mute_minutes: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE antispam_config SET enabled=?, msg_count=?, window_secs=?, mute_minutes=? WHERE id=1",
            (enabled, msg_count, window_secs, mute_minutes),
        )
        await db.commit()


async def set_enabled(enabled: bool) -> None:
    async with get_db() as db:
        await db.execute("UPDATE antispam_config SET enabled=? WHERE id=1", (1 if enabled else 0,))
        await db.commit()


def _prune_state(state: _SpamState, now: float, window: int) -> None:
    while state.timestamps and now - state.timestamps[0] > window:
        state.timestamps.popleft()

    state.seen_media_groups = {
        media_group_id: seen_at
        for media_group_id, seen_at in state.seen_media_groups.items()
        if now - seen_at <= window
    }

    if state.last_event_at and now - state.last_event_at > window:
        state.timestamps.clear()
        state.warning_until = 0.0


def _register_event(state: _SpamState, message: Message, now: float, window: int) -> bool:
    _prune_state(state, now, window)

    media_group_id = message.media_group_id
    if media_group_id:
        if media_group_id in state.seen_media_groups:
            state.last_event_at = now
            return False
        state.seen_media_groups[media_group_id] = now

    state.timestamps.append(now)
    state.last_event_at = now
    return True


async def check_message(message: Message, bot: Bot, config: Config) -> bool:
    cfg = await get_config()
    if not cfg["enabled"]:
        return False

    # Skip bots and moderators
    if not message.from_user or message.from_user.is_bot:
        return False
    if message.from_user.id in config.admin_ids:
        return False

    uid = message.from_user.id if message.from_user else None
    if not uid:
        return False

    chat_id = message.chat.id
    now = datetime.now(timezone.utc).timestamp()
    window = cfg["window_secs"]
    threshold = cfg["msg_count"]
    mute_minutes = cfg["mute_minutes"]

    state = _states[(chat_id, uid)]
    if not _register_event(state, message, now, window):
        return False

    count = len(state.timestamps)

    if count < threshold:
        return False

    if state.warning_until <= now:
        state.warning_until = now + window
        state.timestamps.clear()
        try:
            await message.reply(
                f"⚠️ <b>Предупреждение!</b> Не флудите — замедлитесь.\n"
                f"При повторении может быть выдан мут на {mute_minutes} мин.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        logger.info("Antispam warning: chat=%d uid=%d count=%d/%d", chat_id, uid, count, threshold)
        return True

    until = datetime.now(timezone.utc) + timedelta(minutes=mute_minutes)
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=uid,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
    except Exception as exc:
        logger.error("Antispam mute failed for uid=%d: %s", uid, exc)
        return False

    _states.pop((chat_id, uid), None)

    user_name = message.from_user.full_name or str(uid)
    if message.from_user.username:
        user_name += f" (@{message.from_user.username})"

    try:
        await message.reply(
            f"🔇 <b>{user_name}</b> замучен на {mute_minutes} мин. за флуд.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    try:
        pings = " ".join(f"<a href='tg://user?id={i}'>&#8204;</a>" for i in config.admin_ids)
        await send_message_with_topic(
            bot,
            chat_id=config.moderation_chat_id,
            message_thread_id=config.moderation_topic_id or None,
            topic_name="MODERATION_TOPIC_ID",
            topic_logger=logger,
            text=(
                f"🔇 <b>Антиспам: мут</b>{pings}\n\n"
                f"👤 {user_name} (ID: <code>{uid}</code>)\n"
                f"⏱ На {mute_minutes} мин. за флуд ({count} событий за {window}с)"
            ),
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("Antispam alert failed: %s", exc)

    logger.info("Antispam mute: chat=%d uid=%d mute=%dmin", chat_id, uid, mute_minutes)
    return True
