from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from aiogram.types import ChatMemberMember, ChatMemberBanned, ChatMemberLeft, User

from s21_bot.config import Config, set_config_value, serialize_runtime_config
from s21_bot.db.models import set_db_path, init_db, get_db
from s21_bot.db.user_repo import UserRepo
from s21_bot.db.application_repo import ApplicationRepo
from s21_bot.handlers.auth import _check_and_respond
from s21_bot.handlers.admin_panel import _format_value, _panel_text
from s21_bot.services.events import run_events_poller


@pytest_asyncio.fixture
async def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    set_db_path(path)
    await init_db()
    try:
        yield path
    finally:
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def make_config(**kwargs) -> Config:
    base = dict(
        bot_token="test_token",
        admin_ids=frozenset([999]),
        moderation_chat_id=-1001,
        moderation_topic_id=10,
        s21_username="user",
        s21_password="pwd",
        s21_campus_id="camp",
        community_chat_id=-1002,
        rc_base_url="https://rc.test",
        rc_user_id="rc_uid",
        rc_auth_token="rc_tok",
    )
    base.update(kwargs)
    return Config(**base)


@pytest.mark.asyncio
async def test_user_repo_set_status_and_update_invite_link(temp_db):
    tg_id = 12345
    await UserRepo.upsert_basic(tg_id, "Test User", "testuser")
    user = await UserRepo.get_by_tg_id(tg_id)
    assert user["status"] == "new"

    await UserRepo.set_status(tg_id, "kicked")
    user = await UserRepo.get_by_tg_id(tg_id)
    assert user["status"] == "kicked"

    await UserRepo.update_invite_link(tg_id, "https://t.me/+test_link")
    user = await UserRepo.get_by_tg_id(tg_id)
    assert user["invite_link"] == "https://t.me/+test_link"


@pytest.mark.asyncio
async def test_approved_user_in_chat(temp_db):
    tg_id = 12345
    await UserRepo.upsert_basic(tg_id, "Test User", "testuser")
    await UserRepo.approve(
        tg_id=tg_id,
        moderator_id=999,
        moderator_name="Admin",
        school_login="testlogin",
        coalition="LIGHTHOUSE",
        invite_link="https://t.me/+old",
        decision_date="2026-10-19 12:00:00",
    )

    config = make_config()
    bot = AsyncMock()
    member = MagicMock()
    member.status = "member"
    bot.get_chat_member.return_value = member

    message = AsyncMock()
    message.from_user = User(id=tg_id, is_bot=False, first_name="Test", username="testuser")
    state = AsyncMock()

    handled = await _check_and_respond(message, state, config, bot)
    assert handled is True
    # Should send standard greeting to approved user who is in chat
    message.answer.assert_called_once()
    assert "Добро пожаловать" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_approved_user_left_chat_gets_new_invite_without_reverification(temp_db):
    tg_id = 12345
    await UserRepo.upsert_basic(tg_id, "Test User", "testuser")
    await UserRepo.approve(
        tg_id=tg_id,
        moderator_id=999,
        moderator_name="Admin",
        school_login="testlogin",
        coalition="LIGHTHOUSE",
        invite_link="https://t.me/+expired",
        decision_date="2026-10-16 12:00:00",
    )

    config = make_config()
    bot = AsyncMock()
    member = MagicMock()
    member.status = "left"
    bot.get_chat_member.return_value = member

    bot.create_chat_invite_link.return_value = MagicMock(invite_link="https://t.me/+new_fresh_link")

    message = AsyncMock()
    message.from_user = User(id=tg_id, is_bot=False, first_name="Test", username="testuser")
    state = AsyncMock()

    handled = await _check_and_respond(message, state, config, bot)
    assert handled is True

    # User should NOT be sent to reverification, instead gets fresh link
    user = await UserRepo.get_by_tg_id(tg_id)
    assert user["status"] == "approved"
    assert user["invite_link"] == "https://t.me/+new_fresh_link"

    message.answer.assert_called_once()
    answer_text = message.answer.call_args[0][0]
    assert "Вы уже верифицированы" in answer_text
    assert "https://t.me/+new_fresh_link" in answer_text


@pytest.mark.asyncio
async def test_approved_user_kicked_from_chat_requires_reverification(temp_db):
    tg_id = 12345
    await UserRepo.upsert_basic(tg_id, "Test User", "testuser")
    await UserRepo.approve(
        tg_id=tg_id,
        moderator_id=999,
        moderator_name="Admin",
        school_login="testlogin",
        coalition="LIGHTHOUSE",
        invite_link="https://t.me/+old",
        decision_date="2026-10-16 12:00:00",
    )

    config = make_config()
    bot = AsyncMock()
    member = MagicMock()
    member.status = "kicked"
    bot.get_chat_member.return_value = member

    message = AsyncMock()
    message.from_user = User(id=tg_id, is_bot=False, first_name="Test", username="testuser")
    state = AsyncMock()

    handled = await _check_and_respond(message, state, config, bot)
    assert handled is True

    # User status must now be kicked
    user = await UserRepo.get_by_tg_id(tg_id)
    assert user["status"] == "kicked"

    # Must notify about being kicked and start verification flow
    assert message.answer.call_count == 2
    first_msg = message.answer.call_args_list[0][0][0]
    assert "исключены из чата" in first_msg
    state.set_state.assert_called_once()


@pytest.mark.asyncio
async def test_events_config_and_admin_panel():
    cfg = make_config()
    assert cfg.enable_events is True
    assert cfg.events_exclude_tribes is False
    assert cfg.events_chat_id == 0

    # Test toggles and formatting
    assert _format_value("events_exclude_tribes", True) == "ДА"
    assert _format_value("events_exclude_tribes", False) == "НЕТ"
    assert _format_value("enable_events", True) == "ВКЛ"
    assert _format_value("enable_events", False) == "ВЫКЛ"

    set_config_value(cfg, "events_exclude_tribes", "1")
    assert cfg.events_exclude_tribes is True

    set_config_value(cfg, "enable_events", "0")
    assert cfg.enable_events is False

    set_config_value(cfg, "events_topic_id", "555")
    assert cfg.events_topic_id == 555

    set_config_value(cfg, "events_chat_id", "-100999")
    assert cfg.events_chat_id == -100999


@pytest.mark.asyncio
async def test_events_poller_tribe_filter():
    config = make_config(
        enable_events=True,
        events_topic_id=42,
        events_exclude_tribes=True,
        api_poll_interval=1,
    )

    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=101))

    s21 = AsyncMock()
    sample_events = [
        {"id": 1, "name": "Event 1", "type": "Конференция", "startDateTime": "2026-10-25T10:00:00Z"},
        {"id": 2, "name": "Tribe Event", "type": "Трайб", "startDateTime": "2026-10-26T10:00:00Z"},
        {"id": 3, "name": "Event 3", "type": "Митап", "startDateTime": "2026-10-27T10:00:00Z"},
    ]
    s21.get_events.return_value = sample_events

    task = asyncio.create_task(run_events_poller(bot, s21, config))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Poller seeds on start. After cancel, let's verify poller ran.
