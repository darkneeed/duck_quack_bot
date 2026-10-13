from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
import tempfile
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from s21_bot.db.models import set_db_path, init_db, get_db
from s21_bot.db.application_repo import ApplicationRepo
from s21_bot.db.user_repo import UserRepo
from s21_bot.db.invite_code_repo import InviteCodeRepo
from s21_bot.db.s21_cache_repo import S21CacheRepo
from s21_bot.utils.collections import BoundedSet
from s21_bot.middlewares.ban_check import BanCheckMiddleware
from s21_bot.services.invite import create_one_time_invite
from s21_bot.services.invite_code_service import attach_invite_code_to_request, create_invite_code, AttachResult
from s21_bot.handlers.export import IsModeratorInModChat, _serialize_csv


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


@pytest.mark.asyncio
async def test_database_schema_and_pragmas(temp_db):
    async with get_db() as db:
        # Check pragmas
        async with db.execute("PRAGMA journal_mode;") as cur:
            row = await cur.fetchone()
            assert row[0].lower() == "wal"

        async with db.execute("PRAGMA foreign_keys;") as cur:
            row = await cur.fetchone()
            assert row[0] == 1

        async with db.execute("PRAGMA busy_timeout;") as cur:
            row = await cur.fetchone()
            assert row[0] == 5000

        # Check all 13 tables exist
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table';") as cur:
            tables = {r[0] for r in await cur.fetchall()}

        expected_tables = {
            "users", "applications", "auth_attempts", "otp_sessions",
            "verification_verifiers", "invite_codes", "guest_invites",
            "bot_settings", "join_messages", "s21_cache", "workstation_state",
            "moderators", "antispam_config"
        }
        assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"

        # Check antispam_config default row
        async with db.execute("SELECT * FROM antispam_config WHERE id=1;") as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row["enabled"] == 0

        # Check secondary indexes exist
        async with db.execute("SELECT name FROM sqlite_master WHERE type='index';") as cur:
            indexes = {r[0] for r in await cur.fetchall()}

        expected_indexes = {
            "idx_users_login", "idx_users_status", "idx_applications_tg_id",
            "idx_applications_status", "idx_auth_attempts_tg_time",
            "idx_otp_sessions_tg_live", "idx_verifiers_req_user"
        }
        assert expected_indexes.issubset(indexes), f"Missing indexes: {expected_indexes - indexes}"


@pytest.mark.asyncio
async def test_cas_operations_on_applications(temp_db):
    app_id = await ApplicationRepo.create(
        tg_id=12345,
        tg_name="Test User",
        school_login="tuser",
        user_comment="Hello",
        submitted_at="2026-10-13 12:00:00"
    )

    # First claim succeeds
    claimed1 = await ApplicationRepo.try_claim_and_approve(
        app_id, moderator_id=111, moderator_name="Mod 1", decision_at="2026-10-13 12:01:00"
    )
    assert claimed1 is True

    # Second claim fails
    claimed2 = await ApplicationRepo.try_claim_and_approve(
        app_id, moderator_id=222, moderator_name="Mod 2", decision_at="2026-10-13 12:01:01"
    )
    assert claimed2 is False

    # Try claim and reject on already approved application fails
    rejected = await ApplicationRepo.try_claim_and_reject(
        app_id, moderator_id=333, moderator_name="Mod 3", decision_at="2026-10-13 12:01:02", reject_reason="reason"
    )
    assert rejected is False


@pytest.mark.asyncio
async def test_cas_reject_from_waiting_votes(temp_db):
    app_id = await ApplicationRepo.create(
        tg_id=54321,
        tg_name="Candidate",
        school_login="cand",
        user_comment="Test",
        submitted_at="2026-10-13 12:00:00"
    )
    await ApplicationRepo.set_status(app_id, "waiting_votes")

    rejected = await ApplicationRepo.try_claim_and_reject(
        app_id, moderator_id=111, moderator_name="Mod 1", decision_at="2026-10-13 12:05:00", reject_reason="Rejected"
    )
    assert rejected is True

    # Re-rejecting fails
    rejected2 = await ApplicationRepo.try_claim_and_reject(
        app_id, moderator_id=222, moderator_name="Mod 2", decision_at="2026-10-13 12:06:00", reject_reason="Rejected"
    )
    assert rejected2 is False


@pytest.mark.asyncio
async def test_invite_code_atomic_usage_increment(temp_db):
    code_id = await InviteCodeRepo.create(
        code="TESTCODE",
        creator_user_id=999,
        created_at="2026-10-13 10:00:00",
        usage_limit=1
    )

    # First use succeeds
    ok1 = await InviteCodeRepo.mark_used(code_id, 1001, "2026-10-13 10:01:00")
    assert ok1 is True

    # Second concurrent use fails due to usage_limit
    ok2 = await InviteCodeRepo.mark_used(code_id, 1002, "2026-10-13 10:01:01")
    assert ok2 is False


@pytest.mark.asyncio
async def test_bounded_set():
    bset: BoundedSet[int] = BoundedSet(maxsize=3)
    bset.add(1)
    bset.add(2)
    bset.add(3)
    assert len(bset) == 3
    assert 1 in bset and 2 in bset and 3 in bset

    # Adding a 4th element evicts the oldest (1)
    bset.add(4)
    assert len(bset) == 3
    assert 1 not in bset
    assert 2 in bset and 3 in bset and 4 in bset

    # Re-adding 2 moves it to the end (LRU behavior)
    bset.add(2)
    bset.add(5)
    # Now 3 was oldest, so 3 is evicted
    assert 3 not in bset
    assert 2 in bset and 4 in bset and 5 in bset

    bset.discard(4)
    assert 4 not in bset
    assert len(bset) == 2


@pytest.mark.asyncio
async def test_ban_check_middleware(temp_db):
    # Upsert a banned user and an unbanned user
    await UserRepo.upsert_basic(100, "Banned User")
    await UserRepo.set_banned(100, banned=True)

    await UserRepo.upsert_basic(200, "Clean User")

    middleware = BanCheckMiddleware()

    from aiogram.types import Message, CallbackQuery

    # Banned message test
    msg_banned = MagicMock(spec=Message)
    msg_banned.from_user = MagicMock(id=100)
    msg_banned.answer = AsyncMock()

    next_handler = AsyncMock()
    await middleware(next_handler, msg_banned, {})
    assert not next_handler.called
    assert msg_banned.answer.called

    # Banned callback query test
    cb_banned = MagicMock(spec=CallbackQuery)
    cb_banned.from_user = MagicMock(id=100)
    cb_banned.answer = AsyncMock()

    next_handler.reset_mock()
    await middleware(next_handler, cb_banned, {})
    assert not next_handler.called
    assert cb_banned.answer.called

    # Clean user test
    msg_clean = MagicMock()
    msg_clean.from_user = MagicMock(id=200)
    msg_clean.chat = MagicMock(id=999)
    next_handler.reset_mock()
    await middleware(next_handler, msg_clean, {})
    assert next_handler.called


@pytest.mark.asyncio
async def test_export_debug_filter():
    filt = IsModeratorInModChat()

    config = MagicMock()
    config.admin_ids = [111, 222]
    config.moderation_chat_id = -100999

    # Valid moderator in mod chat
    msg_valid = MagicMock()
    msg_valid.from_user = MagicMock(id=111)
    msg_valid.chat = MagicMock(id=-100999)
    assert await filt(msg_valid, config) is True

    # Valid moderator in different chat
    msg_wrong_chat = MagicMock()
    msg_wrong_chat.from_user = MagicMock(id=111)
    msg_wrong_chat.chat = MagicMock(id=-100111)
    assert await filt(msg_wrong_chat, config) is False

    # Non-moderator in mod chat
    msg_non_mod = MagicMock()
    msg_non_mod.from_user = MagicMock(id=333)
    msg_non_mod.chat = MagicMock(id=-100999)
    assert await filt(msg_non_mod, config) is False


@pytest.mark.asyncio
async def test_invite_expire_date():
    bot = MagicMock()
    bot.create_chat_invite_link = AsyncMock(return_value=MagicMock(invite_link="https://t.me/+abc"))

    link = await create_one_time_invite(bot, chat_id=-100123, expire_seconds=3600, name="test")
    assert link == "https://t.me/+abc"

    call_args = bot.create_chat_invite_link.call_args
    assert call_args is not None
    _, kwargs = call_args
    assert kwargs["expire_date"] is not None
    assert isinstance(kwargs["expire_date"], datetime)
    assert kwargs["expire_date"].tzinfo is not None


@pytest.mark.asyncio
async def test_social_trust_deadlock_prevention(temp_db):
    from s21_bot.services.social_trust import run_social_trust

    app_id = await ApplicationRepo.create(
        tg_id=8888,
        tg_name="Deadlock Candidate",
        school_login="deadlock",
        user_comment="none",
        submitted_at="2026-10-13 12:00:00"
    )

    s21 = MagicMock()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    config = MagicMock()
    config.social_trust_project_ids = []
    config.moderation_chat_id = -100123
    config.moderation_topic_id = None

    # Mock teammate resolver returning empty list of teammates
    with patch("s21_bot.services.social_trust.get_candidate_teammates", AsyncMock(return_value=[])):
        with patch("s21_bot.services.social_trust.resolve_teammates_to_users", AsyncMock(return_value=[])):
            await run_social_trust(app_id, "deadlock", "Deadlock Candidate", bot, config, s21)

    app = await ApplicationRepo.get(app_id)
    assert app is not None
    assert app["status"] == "pending", f"Expected 'pending' status but found '{app['status']}'"


@pytest.mark.asyncio
async def test_user_repo_guest_approval_and_export(temp_db):
    await UserRepo.upsert_basic(555, "Guest User")
    await UserRepo.approve_as_guest(
        tg_id=555,
        school_login="guest_login",
        coalition="Alliance",
        invite_link="https://t.me/+guest",
        home_campus="Moscow",
        decision_date="2026-10-13 12:00:00",
        moderator_id=1,
        moderator_name="Admin"
    )

    user = await UserRepo.get_by_tg_id(555)
    assert user is not None
    assert user["status"] == "approved"
    assert user["is_guest"] == 1
    assert user["school_login"] == "guest_login"

    u_cols, u_rows = await UserRepo.get_all_for_export()
    assert "tg_id" in u_cols
    assert len(u_rows) >= 1

    a_cols, a_rows = await ApplicationRepo.get_all_for_export()
    assert "id" in a_cols


@pytest.mark.asyncio
async def test_s21_cache_get_all_entries(temp_db):
    await S21CacheRepo.set("user1", {"info": {"expValue": 100}}, "2026-10-13 12:00:00")
    await S21CacheRepo.set("user2", {"info": {"expValue": 200}}, "2026-10-13 12:00:00")

    entries = await S21CacheRepo.get_all_entries()
    assert len(entries) == 2
    logins = {e[0] for e in entries}
    assert logins == {"user1", "user2"}


@pytest.mark.asyncio
async def test_chat_moderation_cmd_mute_no_name_error():
    from s21_bot.handlers.chat_moderation import cmd_mute

    message = MagicMock()
    message.text = "/mute 123456 30 reason"
    message.reply_to_message = None
    message.reply = AsyncMock()

    bot = MagicMock()
    bot.restrict_chat_member = AsyncMock()
    bot.get_chat_member = AsyncMock(return_value=MagicMock(user=MagicMock(full_name="Target User")))

    config = MagicMock()
    config.community_chat_id = -1001
    config.admin_ids = []

    # Should not raise NameError: name '_parse_reply_or_id' is not defined
    await cmd_mute(message, bot, config)
    assert bot.restrict_chat_member.called


@pytest.mark.asyncio
async def test_where_cmd_peers_no_api_starvation(temp_db):
    from s21_bot.handlers.where import cmd_peers

    # Create approved user without cache
    await UserRepo.upsert_basic(999, "Peer User")
    await UserRepo.approve(
        tg_id=999, moderator_id=1, moderator_name="Admin",
        school_login="nocache_peer", coalition="test", invite_link="link", decision_date="now"
    )

    message = MagicMock()
    message.text = "/peers python"
    message.chat = MagicMock(type="supergroup")
    message.from_user = MagicMock(id=999)
    wait_msg = MagicMock()
    wait_msg.delete = AsyncMock()
    message.answer = AsyncMock(side_effect=[wait_msg, None])

    s21 = MagicMock()
    s21.get_active_projects = AsyncMock()

    config = MagicMock()
    config.cmd_peers_scope = "BOTH"

    await cmd_peers(message, s21, config)

    # get_active_projects MUST NOT be called in loop when cache is missing
    assert not s21.get_active_projects.called


@pytest.mark.asyncio
async def test_s21_api_lock_and_timeout():
    from s21_bot.services.s21_api import S21Client
    from s21_bot.services.rocketchat import RocketChatClient
    import aiohttp

    client = S21Client("user", "pass")
    assert hasattr(client, "_auth_lock")
    assert isinstance(client._auth_lock, asyncio.Lock)

    rc = RocketChatClient("http://rc.local", "uid", "tok")
    # Verify timeout initialization on start
    with patch("aiohttp.ClientSession") as mock_session_cls:
        await rc.start()
        assert mock_session_cls.called
        _, kwargs = mock_session_cls.call_args
        assert "timeout" in kwargs
        assert kwargs["timeout"].total == 15.0
        assert kwargs["timeout"].connect == 5.0


@pytest.mark.asyncio
async def test_approve_failure_status_rollback(temp_db):
    from s21_bot.handlers.moderation import cb_approve
    from s21_bot.handlers.admin_users import cmd_approve

    app_id = await ApplicationRepo.create(
        tg_id=777,
        tg_name="Rollback Candidate",
        school_login="rollback_user",
        user_comment="none",
        submitted_at="2026-10-13 12:00:00"
    )

    cb = MagicMock()
    cb.data = f"approve:{app_id}"
    cb.from_user = MagicMock(id=1, full_name="Mod 1")
    cb.answer = AsyncMock()

    bot = MagicMock()
    config = MagicMock()
    config.community_chat_id = -100123
    config.invite_link_expire_seconds = 3600
    config.moderation_chat_id = -100999
    config.moderation_topic_id = None
    s21 = MagicMock()

    with patch("s21_bot.services.invite.create_one_time_invite", AsyncMock(side_effect=RuntimeError("Telegram API down"))):
        with patch("s21_bot.handlers.moderation._alert_error", AsyncMock()):
            await cb_approve(cb, bot, config, s21)

    app = await ApplicationRepo.get(app_id)
    assert app is not None
    assert app["status"] == "pending", f"Expected rollback to 'pending', got '{app['status']}'"

    # Also test cmd_approve rollback
    msg = MagicMock()
    msg.text = f"/approve {app_id}"
    msg.from_user = MagicMock(id=1, full_name="Admin", username="admin")
    msg.reply = AsyncMock()

    with patch("s21_bot.services.invite.create_one_time_invite", AsyncMock(side_effect=RuntimeError("Telegram API down"))):
        await cmd_approve(msg, bot, config, s21)

    app2 = await ApplicationRepo.get(app_id)
    assert app2 is not None
    assert app2["status"] == "pending", f"Expected rollback to 'pending', got '{app2['status']}'"


@pytest.mark.asyncio
async def test_cooldown_rejection_race_handling(temp_db):
    from s21_bot.handlers.moderation import cb_cooldown
    from aiogram.fsm.context import FSMContext

    app_id = await ApplicationRepo.create(
        tg_id=444,
        tg_name="Race Candidate",
        school_login="race_user",
        user_comment="none",
        submitted_at="2026-10-13 12:00:00"
    )

    # First approve the application
    await ApplicationRepo.try_claim_and_approve(app_id, 1, "Mod 1", "now")

    cb = MagicMock()
    cb.data = f"cooldown:{app_id}:3600"
    cb.from_user = MagicMock(id=2, full_name="Mod 2")
    cb.answer = AsyncMock()
    cb.message = MagicMock()
    cb.message.delete = AsyncMock()

    state = MagicMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"reject_reason": "test"})
    state.clear = AsyncMock()

    bot = MagicMock()
    config = MagicMock()

    await cb_cooldown(cb, state, bot, config)

    # cb.answer should have been called with show_alert=True notifying already decided
    assert cb.answer.called
    assert cb.answer.call_args[1].get("show_alert") is True


@pytest.mark.asyncio
async def test_social_trust_zero_sent_reverts_to_pending(temp_db):
    from s21_bot.services.social_trust import run_social_trust, NotifyStats

    app_id = await ApplicationRepo.create(
        tg_id=333,
        tg_name="No-Sent Candidate",
        school_login="nosent",
        user_comment="none",
        submitted_at="2026-10-13 12:00:00"
    )

    bot = MagicMock()
    config = MagicMock()
    config.social_trust_project_ids = []
    config.moderation_chat_id = -100123
    config.moderation_topic_id = None
    s21 = MagicMock()

    users = [{"tg_id": 999, "school_login": "tm999", "tg_name": "Teammate"}]
    with patch("s21_bot.services.social_trust.get_candidate_teammates", AsyncMock(return_value=["tm999"])):
        with patch("s21_bot.services.social_trust.resolve_teammates_to_users", AsyncMock(return_value=users)):
            with patch("s21_bot.services.social_trust.attach_teammates_to_request", AsyncMock()):
                with patch("s21_bot.services.social_trust.send_verification_requests", AsyncMock(return_value=NotifyStats(sent=0, failed=1))):
                    with patch("s21_bot.services.social_trust._alert_moderators_no_teammates", AsyncMock()):
                        await run_social_trust(app_id, "nosent", "No-Sent Candidate", bot, config, s21)

    app = await ApplicationRepo.get(app_id)
    assert app is not None
    assert app["status"] == "pending", f"Expected revert to 'pending', got '{app['status']}'"


@pytest.mark.asyncio
async def test_social_trust_pipeline_exception_reverts_to_pending(temp_db):
    from s21_bot.services.social_trust import run_social_trust

    app_id = await ApplicationRepo.create(
        tg_id=222,
        tg_name="Crash Candidate",
        school_login="crash",
        user_comment="none",
        submitted_at="2026-10-13 12:00:00"
    )

    bot = MagicMock()
    config = MagicMock()
    config.social_trust_project_ids = []
    s21 = MagicMock()

    with patch("s21_bot.services.social_trust.get_candidate_teammates", AsyncMock(side_effect=RuntimeError("S21 API Down"))):
        await run_social_trust(app_id, "crash", "Crash Candidate", bot, config, s21)

    app = await ApplicationRepo.get(app_id)
    assert app is not None
    assert app["status"] == "pending", f"Expected revert to 'pending' on exception, got '{app['status']}'"


@pytest.mark.asyncio
async def test_bounded_set_extended_features():
    bs = BoundedSet[int](maxsize=4, iterable=[1, 2, 3])
    assert len(bs) == 3
    assert repr(bs) == "BoundedSet([1, 2, 3], maxsize=4)"

    bs.update([4, 5])
    # 1 should be evicted because maxsize=4
    assert len(bs) == 4
    assert 1 not in bs
    assert list(bs) == [2, 3, 4, 5]

    bs_copy = bs.copy()
    assert bs_copy is not bs
    assert list(bs_copy) == [2, 3, 4, 5]


