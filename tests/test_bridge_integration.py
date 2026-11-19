from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp
import pytest
from aiogram.types import (
    Chat,
    ChatMemberAdministrator,
    ChatMemberBanned,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    Message,
    User,
    WebAppInfo,
)


class FakeResponse:
    """Helper mock for aiohttp client responses."""

    def __init__(self, status: int, json_data: dict | list | None = None, text_data: str = ""):
        self.status = status
        self._json_data = json_data if json_data is not None else {}
        self._text_data = text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=self.status,
                message=f"HTTP {self.status}",
            )

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data


def _get_bridge_client_class():
    from s21_bot.services.bridge_client import BridgeClient

    return BridgeClient


def _get_bridge_state_class():
    from s21_bot.services.bridge_state import BridgeState

    return BridgeState


SAMPLE_CONFIG_RESPONSE = {
    "runtime_config": {
        "moderation_topic_id": 100,
        "notify_topic_id": 101,
        "events_topic_id": 102,
        "failed_auth_topic_id": 103,
        "workstation_topic_id": 104,
        "newcomer_topic_id": 105,
        "digest_topic_id": 106,
        "enable_digest": True,
        "enable_workstation": True,
        "enable_newcomer": True,
        "enable_events": True,
        "auto_delete_join_messages": False,
        "invite_link_expire_seconds": 86400,
        "command_scopes": {
            "cmd_where_scope": "BOTH",
            "cmd_peer_scope": "PRIVATE",
        },
        "branding": {
            "community_name": "Школы 21",
            "community_city": "Волгоград",
        },
    },
    "approved_chats": [
        {
            "tg_chat_id": -1001234567890,
            "title": "Core 2024",
            "chat_type": "supergroup",
            "config_json": {
                "welcome_message_enabled": True,
                "welcome_message_text": "Привет!",
                "welcome_message_delete_after_minutes": 10,
                "auto_delete_join_messages": True,
                "antispam_enabled": True,
                "antispam_limit": 5,
                "antispam_window_seconds": 5,
                "antispam_mute_minutes": 15,
                "filter_links_enabled": True,
            },
        }
    ],
}


# ============================================================================
# 1. BridgeClient.fetch_config() Tests
# ============================================================================


@pytest.mark.asyncio
async def test_fetch_config_sends_x_bridge_secret_header():
    """Verify that fetch_config sends the X-Bridge-Secret header to GET /api/v1/bridge/config."""
    BridgeClient = _get_bridge_client_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="test-secret-key-123",
        state=state,
    )

    captured_url = None
    captured_headers = None

    def mock_get(url, headers=None, **kwargs):
        nonlocal captured_url, captured_headers
        captured_url = url
        captured_headers = headers
        return FakeResponse(200, SAMPLE_CONFIG_RESPONSE)

    mock_session = MagicMock()
    mock_session.get.side_effect = mock_get
    client._session = mock_session

    result = await client.fetch_config()

    assert captured_url == "https://quack-21.mwnd.tech/api/v1/bridge/config"
    assert captured_headers is not None
    assert captured_headers.get("X-Bridge-Secret") == "test-secret-key-123"
    assert result is not None


@pytest.mark.asyncio
async def test_fetch_config_parses_runtime_config_and_approved_chats():
    """Verify parsing of runtime_config and approved_chats into BridgeState."""
    BridgeClient = _get_bridge_client_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="secret",
        state=state,
    )

    mock_session = MagicMock()
    mock_session.get.return_value = FakeResponse(200, SAMPLE_CONFIG_RESPONSE)
    client._session = mock_session

    await client.fetch_config()

    # Check BridgeState
    assert state.is_chat_approved(-1001234567890) is True
    assert state.is_chat_approved(-1009999999999) is False
    assert state.get_approved_chat_ids() == {-1001234567890}

    chat_cfg = state.get_chat_config(-1001234567890)
    assert chat_cfg is not None
    assert chat_cfg.get("welcome_message_enabled") is True
    assert chat_cfg.get("antispam_limit") == 5


@pytest.mark.asyncio
async def test_fetch_config_caches_settings_for_60_seconds():
    """Verify that fetch_config caches active settings in BridgeState for 60 seconds."""
    BridgeClient = _get_bridge_client_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="secret",
        state=state,
        sync_interval=60,
    )

    mock_session = MagicMock()
    mock_session.get.return_value = FakeResponse(200, SAMPLE_CONFIG_RESPONSE)
    client._session = mock_session

    await client.fetch_config()
    assert state.is_cache_fresh() is True

    # Advance time artificially past 60s
    with patch("time.time", return_value=state.last_sync_timestamp + 61):
        assert state.is_cache_fresh() is False


@pytest.mark.asyncio
async def test_fetch_config_graceful_degradation_on_500():
    """Verify that when bridge returns 500, cached configuration is retained."""
    BridgeClient = _get_bridge_client_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    # Pre-populate state
    state.update(
        runtime_config={"moderation_topic_id": 50},
        approved_chats=[{"tg_chat_id": -100555, "title": "Old Chat", "config_json": {}}],
    )
    assert state.is_chat_approved(-100555) is True

    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="secret",
        state=state,
    )

    mock_session = MagicMock()
    mock_session.get.return_value = FakeResponse(500, {"detail": "Internal Server Error"})
    client._session = mock_session

    # fetch_config must handle 500 without crashing and retain cached config
    result = await client.fetch_config()

    assert state.is_chat_approved(-100555) is True
    assert -100555 in state.get_approved_chat_ids()
    assert result is None or result is False or isinstance(result, dict)


@pytest.mark.asyncio
async def test_fetch_config_graceful_degradation_on_network_timeout():
    """Verify that when bridge times out, cached configuration is retained."""
    BridgeClient = _get_bridge_client_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    state.update(
        runtime_config={"moderation_topic_id": 50},
        approved_chats=[{"tg_chat_id": -100777, "title": "Saved Chat", "config_json": {}}],
    )

    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="secret",
        state=state,
    )

    mock_session = MagicMock()
    mock_session.get.side_effect = asyncio.TimeoutError("Connection timed out")
    client._session = mock_session

    await client.fetch_config()

    # Cached state must remain intact
    assert state.is_chat_approved(-100777) is True


@pytest.mark.asyncio
async def test_fetch_config_rejection_on_401_or_403():
    """Verify that 401 or 403 (unauthorized/forbidden) does not corrupt state and is handled."""
    BridgeClient = _get_bridge_client_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="wrong-secret",
        state=state,
    )

    mock_session = MagicMock()
    mock_session.get.return_value = FakeResponse(401, {"detail": "Invalid secret"})
    client._session = mock_session

    # Should handle 401 cleanly
    result_401 = await client.fetch_config()
    assert result_401 is None or result_401 is False

    mock_session.get.return_value = FakeResponse(403, {"detail": "Forbidden"})
    result_403 = await client.fetch_config()
    assert result_403 is None or result_403 is False


@pytest.mark.asyncio
async def test_fetch_config_empty_approved_chats_updates_state():
    """Verify that if bridge returns empty approved_chats, approved chat list is empty."""
    BridgeClient = _get_bridge_client_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    state.update(
        runtime_config={},
        approved_chats=[{"tg_chat_id": -100111, "title": "Old", "config_json": {}}],
    )

    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="secret",
        state=state,
    )

    empty_response = {"runtime_config": {}, "approved_chats": []}
    mock_session = MagicMock()
    mock_session.get.return_value = FakeResponse(200, empty_response)
    client._session = mock_session

    await client.fetch_config()

    assert state.is_chat_approved(-100111) is False
    assert len(state.get_approved_chat_ids()) == 0


# ============================================================================
# 2. BridgeClient.report_chat_event() Tests
# ============================================================================


@pytest.mark.asyncio
async def test_report_chat_event_added():
    """Verify report_chat_event with action='added' sends expected POST payload."""
    BridgeClient = _get_bridge_client_class()

    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="test-secret",
    )

    captured_url = None
    captured_json = None
    captured_headers = None

    def mock_post(url, json=None, headers=None, **kwargs):
        nonlocal captured_url, captured_json, captured_headers
        captured_url = url
        captured_json = json
        captured_headers = headers
        return FakeResponse(200, {"ok": True, "status": "pending_approval"})

    mock_session = MagicMock()
    mock_session.post.side_effect = mock_post
    client._session = mock_session

    resp = await client.report_chat_event(
        tg_chat_id=-100123456,
        title="Волгоград Кампус",
        chat_type="supergroup",
        action="added",
    )

    assert captured_url == "https://quack-21.mwnd.tech/api/v1/bridge/chats/event"
    assert captured_headers.get("X-Bridge-Secret") == "test-secret"
    assert captured_json == {
        "tg_chat_id": -100123456,
        "title": "Волгоград Кампус",
        "chat_type": "supergroup",
        "action": "added",
    }
    assert resp is not None


@pytest.mark.asyncio
async def test_report_chat_event_removed():
    """Verify report_chat_event with action='removed'."""
    BridgeClient = _get_bridge_client_class()

    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="test-secret",
    )

    captured_json = None

    def mock_post(url, json=None, **kwargs):
        nonlocal captured_json
        captured_json = json
        return FakeResponse(200, {"ok": True, "status": "rejected"})

    mock_session = MagicMock()
    mock_session.post.side_effect = mock_post
    client._session = mock_session

    await client.report_chat_event(
        tg_chat_id=-100123456,
        title="Волгоград Кампус",
        chat_type="supergroup",
        action="removed",
    )

    assert captured_json["action"] == "removed"


@pytest.mark.asyncio
async def test_report_chat_event_rights_changed():
    """Verify report_chat_event with action='rights_changed'."""
    BridgeClient = _get_bridge_client_class()

    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="test-secret",
    )

    captured_json = None

    def mock_post(url, json=None, **kwargs):
        nonlocal captured_json
        captured_json = json
        return FakeResponse(200, {"ok": True, "status": "approved"})

    mock_session = MagicMock()
    mock_session.post.side_effect = mock_post
    client._session = mock_session

    await client.report_chat_event(
        tg_chat_id=-100123456,
        title="Волгоград Кампус",
        chat_type="supergroup",
        action="rights_changed",
    )

    assert captured_json["action"] == "rights_changed"


@pytest.mark.asyncio
async def test_report_chat_event_invalid_action_raises_value_error():
    """Verify that an unsupported action raises ValueError before sending HTTP request."""
    BridgeClient = _get_bridge_client_class()

    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="test-secret",
    )

    mock_session = MagicMock()
    client._session = mock_session

    with pytest.raises(ValueError):
        await client.report_chat_event(
            tg_chat_id=-100123456,
            title="Chat",
            chat_type="group",
            action="deleted",  # Invalid action
        )

    assert not mock_session.post.called


# ============================================================================
# 3. BridgeClient.lookup_peer() Tests
# ============================================================================


@pytest.mark.asyncio
async def test_lookup_peer_success():
    """Verify proxy peer lookup via GET /api/v1/bridge/s21/peer/{login}."""
    BridgeClient = _get_bridge_client_class()

    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="secret-xyz",
    )

    captured_url = None
    captured_headers = None

    def mock_get(url, headers=None, **kwargs):
        nonlocal captured_url, captured_headers
        captured_url = url
        captured_headers = headers
        return FakeResponse(200, {"login": "darkned", "status": "active", "campus": "Волгоград"})

    mock_session = MagicMock()
    mock_session.get.side_effect = mock_get
    client._session = mock_session

    peer_data = await client.lookup_peer("darkned")

    assert captured_url == "https://quack-21.mwnd.tech/api/v1/bridge/s21/peer/darkned"
    assert captured_headers.get("X-Bridge-Secret") == "secret-xyz"
    assert peer_data is not None
    assert peer_data.get("login") == "darkned"


@pytest.mark.asyncio
async def test_lookup_peer_not_found_returns_none():
    """Verify peer lookup returns None when peer is not found (404)."""
    BridgeClient = _get_bridge_client_class()

    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="secret",
    )

    mock_session = MagicMock()
    mock_session.get.return_value = FakeResponse(404, {"detail": "Peer not found"})
    client._session = mock_session

    peer_data = await client.lookup_peer("nonexistent_user")
    assert peer_data is None


# ============================================================================
# 4. my_chat_member Event Handler Tests
# ============================================================================


@pytest.mark.asyncio
async def test_my_chat_member_bot_added_to_group():
    """Verify that adding bot to group triggers report_chat_event('added')."""
    from s21_bot.handlers.bridge_chats import on_my_chat_member

    bot_user = User(id=111111, is_bot=True, first_name="KryakenBot", username="kryaken_bot")
    chat = Chat(id=-1001234567, type="supergroup", title="Волгоград Волна 1")

    update = MagicMock(spec=ChatMemberUpdated)
    update.chat = chat
    update.old_chat_member = ChatMemberLeft(user=bot_user)
    update.new_chat_member = ChatMemberMember(user=bot_user)

    mock_bridge = AsyncMock()

    await on_my_chat_member(update, bridge_client=mock_bridge)

    mock_bridge.report_chat_event.assert_called_once_with(
        tg_chat_id=-1001234567,
        title="Волгоград Волна 1",
        chat_type="supergroup",
        action="added",
    )


@pytest.mark.asyncio
async def test_my_chat_member_bot_added_as_admin():
    """Verify that adding bot as administrator triggers report_chat_event('added')."""
    from s21_bot.handlers.bridge_chats import on_my_chat_member

    bot_user = User(id=111111, is_bot=True, first_name="KryakenBot", username="kryaken_bot")
    chat = Chat(id=-1009876543, type="group", title="Рабочий чат")

    update = MagicMock(spec=ChatMemberUpdated)
    update.chat = chat
    update.old_chat_member = ChatMemberLeft(user=bot_user)
    update.new_chat_member = ChatMemberAdministrator(
        user=bot_user,
        can_be_edited=False,
        is_anonymous=False,
        can_manage_chat=True,
        can_delete_messages=True,
        can_manage_video_chats=False,
        can_restrict_members=True,
        can_promote_members=False,
        can_change_info=True,
        can_invite_users=True,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
    )

    mock_bridge = AsyncMock()

    await on_my_chat_member(update, bridge_client=mock_bridge)

    mock_bridge.report_chat_event.assert_called_once_with(
        tg_chat_id=-1009876543,
        title="Рабочий чат",
        chat_type="group",
        action="added",
    )


@pytest.mark.asyncio
async def test_my_chat_member_bot_removed_from_group():
    """Verify that kicking or removing bot triggers report_chat_event('removed')."""
    from s21_bot.handlers.bridge_chats import on_my_chat_member

    bot_user = User(id=111111, is_bot=True, first_name="KryakenBot", username="kryaken_bot")
    chat = Chat(id=-1001234567, type="supergroup", title="Волгоград Волна 1")

    update = MagicMock(spec=ChatMemberUpdated)
    update.chat = chat
    update.old_chat_member = ChatMemberMember(user=bot_user)
    update.new_chat_member = ChatMemberBanned(user=bot_user, until_date=0)

    mock_bridge = AsyncMock()

    await on_my_chat_member(update, bridge_client=mock_bridge)

    mock_bridge.report_chat_event.assert_called_once_with(
        tg_chat_id=-1001234567,
        title="Волгоград Волна 1",
        chat_type="supergroup",
        action="removed",
    )


@pytest.mark.asyncio
async def test_my_chat_member_bot_rights_changed():
    """Verify that promoting/demoting bot rights triggers report_chat_event('rights_changed')."""
    from s21_bot.handlers.bridge_chats import on_my_chat_member

    bot_user = User(id=111111, is_bot=True, first_name="KryakenBot", username="kryaken_bot")
    chat = Chat(id=-1001234567, type="supergroup", title="Волгоград Волна 1")

    update = MagicMock(spec=ChatMemberUpdated)
    update.chat = chat
    update.old_chat_member = ChatMemberMember(user=bot_user)
    update.new_chat_member = ChatMemberAdministrator(
        user=bot_user,
        can_be_edited=False,
        is_anonymous=False,
        can_manage_chat=True,
        can_delete_messages=True,
        can_manage_video_chats=False,
        can_restrict_members=True,
        can_promote_members=False,
        can_change_info=True,
        can_invite_users=True,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
    )

    mock_bridge = AsyncMock()

    await on_my_chat_member(update, bridge_client=mock_bridge)

    mock_bridge.report_chat_event.assert_called_once_with(
        tg_chat_id=-1001234567,
        title="Волгоград Волна 1",
        chat_type="supergroup",
        action="rights_changed",
    )


@pytest.mark.asyncio
async def test_my_chat_member_private_chat_ignored():
    """Verify that private chat member updates are ignored and not sent to bridge."""
    from s21_bot.handlers.bridge_chats import on_my_chat_member

    bot_user = User(id=111111, is_bot=True, first_name="KryakenBot", username="kryaken_bot")
    chat = Chat(id=12345678, type="private")

    update = MagicMock(spec=ChatMemberUpdated)
    update.chat = chat
    update.old_chat_member = ChatMemberLeft(user=bot_user)
    update.new_chat_member = ChatMemberMember(user=bot_user)

    mock_bridge = AsyncMock()

    await on_my_chat_member(update, bridge_client=mock_bridge)

    assert not mock_bridge.report_chat_event.called


# ============================================================================
# 5. Bot Navigation & Mini App (/kryaken) Tests
# ============================================================================


@pytest.mark.asyncio
async def test_cmd_kryaken_generates_card_with_webapp_info():
    """Verify that /kryaken command answers with an inline card containing WebAppInfo URL."""
    from s21_bot.handlers.kryaken import cmd_kryaken

    message = MagicMock(spec=Message)
    message.text = "/kryaken"
    message.chat = Chat(id=12345, type="private")
    message.answer = AsyncMock()

    await cmd_kryaken(message)

    message.answer.assert_called_once()
    call_args = message.answer.call_args
    assert call_args is not None

    # Inspect reply_markup
    reply_markup = call_args.kwargs.get("reply_markup")
    assert isinstance(reply_markup, InlineKeyboardMarkup)

    # Find the Mini App button
    found_webapp = False
    for row in reply_markup.inline_keyboard:
        for btn in row:
            if btn.web_app and isinstance(btn.web_app, WebAppInfo):
                assert btn.web_app.url == "https://quack-21.mwnd.tech"
                found_webapp = True

    assert found_webapp is True, "WebApp button with https://quack-21.mwnd.tech not found in inline keyboard"


@pytest.mark.asyncio
async def test_setup_kryaken_menu_button():
    """Verify helper configuring Telegram chat menu button for Mini App."""
    from s21_bot.handlers.kryaken import setup_kryaken_menu

    bot = AsyncMock()

    await setup_kryaken_menu(bot)

    bot.set_chat_menu_button.assert_called_once()
    call_args = bot.set_chat_menu_button.call_args
    menu_button = call_args.kwargs.get("menu_button")
    assert menu_button is not None
    assert getattr(menu_button, "web_app", None) is not None
    assert menu_button.web_app.url == "https://quack-21.mwnd.tech"


# ============================================================================
# 6. Tier 2 Edge & Boundary Cases
# ============================================================================


@pytest.mark.asyncio
async def test_bridge_client_start_sync_task_and_close():
    """Verify that start_sync_task runs background polling and close cancels it cleanly."""
    BridgeClient = _get_bridge_client_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    client = BridgeClient(
        bridge_url="https://quack-21.mwnd.tech",
        bridge_secret="secret",
        state=state,
        sync_interval=1,
    )

    fetch_call_count = 0

    async def mock_fetch():
        nonlocal fetch_call_count
        fetch_call_count += 1
        return {"runtime_config": {}, "approved_chats": []}

    client.fetch_config = mock_fetch

    sync_task = client.start_sync_task(interval_seconds=1)
    assert not sync_task.done()

    # Allow one iteration to run
    await asyncio.sleep(0.05)
    assert fetch_call_count >= 1

    await client.close()
    assert sync_task.cancelled() or sync_task.done()


def test_bridge_state_command_scope_resolution():
    """Verify command scope resolution for direct matches, prefixes, and defaults."""
    BridgeState = _get_bridge_state_class()
    state = BridgeState()

    state.update(
        runtime_config={
            "command_scopes": {
                "kryaken": "PRIVATE",
                "cmd_where_scope": "PUBLIC",
                "profile": "OFF",
            }
        },
        approved_chats=[],
    )

    assert state.get_command_scope("kryaken") == "PRIVATE"
    assert state.get_command_scope("/kryaken") == "PRIVATE"
    assert state.get_command_scope("where") == "PUBLIC"
    assert state.get_command_scope("/where") == "PUBLIC"
    assert state.get_command_scope("profile") == "OFF"
    assert state.get_command_scope("unknown_cmd") == "all"


def test_bridge_state_chat_id_coercion_and_edge_cases():
    """Verify handling of string chat IDs, invalid types, and empty configs."""
    BridgeState = _get_bridge_state_class()
    state = BridgeState()

    state.update(
        runtime_config={},
        approved_chats=[
            {"tg_chat_id": "-10012345", "title": "String ID Chat", "config_json": {"custom": 42}},
            {"tg_chat_id": "invalid_not_an_int", "title": "Bad ID Chat"},
            {"title": "Missing ID Chat"},
            "not_even_a_dict",  # type: ignore
        ],
    )

    assert state.is_chat_approved(-10012345) is True
    assert state.is_chat_approved("-10012345") is True
    assert state.is_chat_approved("invalid") is False
    assert state.get_chat_config(-10012345) == {"custom": 42}
    assert state.get_chat_config(999999) == {}


@pytest.mark.asyncio
async def test_cmd_kryaken_scope_off_silence():
    """Verify that when command scope is OFF, /kryaken produces no response."""
    from s21_bot.handlers.kryaken import cmd_kryaken

    BridgeState = _get_bridge_state_class()
    state = BridgeState()
    state.update(runtime_config={"command_scopes": {"kryaken": "OFF"}}, approved_chats=[])

    message = MagicMock(spec=Message)
    message.chat = Chat(id=12345, type="private")
    message.answer = AsyncMock()

    await cmd_kryaken(message, bridge_state=state)
    assert not message.answer.called


@pytest.mark.asyncio
async def test_cmd_kryaken_scope_private_in_public_declines():
    """Verify that when scope is PRIVATE, running /kryaken in group chat gives informative notice."""
    from s21_bot.handlers.kryaken import cmd_kryaken

    BridgeState = _get_bridge_state_class()
    state = BridgeState()
    state.update(runtime_config={"command_scopes": {"kryaken": "PRIVATE"}}, approved_chats=[])

    message = MagicMock(spec=Message)
    message.chat = Chat(id=-100999, type="supergroup")
    message.answer = AsyncMock()

    await cmd_kryaken(message, bridge_state=state)
    message.answer.assert_called_once()
    assert "только в личных сообщениях" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_cmd_kryaken_scope_public_in_private_declines():
    """Verify that when scope is PUBLIC, running /kryaken in private chat gives informative notice."""
    from s21_bot.handlers.kryaken import cmd_kryaken

    BridgeState = _get_bridge_state_class()
    state = BridgeState()
    state.update(runtime_config={"command_scopes": {"kryaken": "PUBLIC"}}, approved_chats=[])

    message = MagicMock(spec=Message)
    message.chat = Chat(id=12345, type="private")
    message.answer = AsyncMock()

    await cmd_kryaken(message, bridge_state=state)
    message.answer.assert_called_once()
    assert "только в групповых чатах" in message.answer.call_args.args[0]


def test_main_polling_allowed_updates_contains_my_chat_member():
    """Verify TC-S21B-02-3: main.py explicitly configures 'my_chat_member' in allowed_updates."""
    import inspect
    from s21_bot import main

    source = inspect.getsource(main)
    assert '"my_chat_member"' in source or "'my_chat_member'" in source


def test_main_registers_callback_query_chat_approval_middleware():
    """Verify that main.py registers ChatApprovalMiddleware on callback_query."""
    import inspect
    from s21_bot import main

    source = inspect.getsource(main)
    assert "dp.callback_query.middleware(ChatApprovalMiddleware(bridge_state=bridge_state))" in source


def test_bridge_state_get_chat_config_defensive_copy():
    """Verify that get_chat_config returns a defensive copy to prevent cache mutation."""
    BridgeState = _get_bridge_state_class()
    state = BridgeState()

    state.update(
        runtime_config={},
        approved_chats=[
            {
                "tg_chat_id": -10042,
                "title": "Immutable Chat",
                "config_json": {"antispam_limit": 5, "nested": {"key": "value"}},
            }
        ],
    )

    cfg1 = state.get_chat_config(-10042)
    assert cfg1["antispam_limit"] == 5

    # Mutate returned dictionary
    cfg1["antispam_limit"] = 999
    cfg1["new_injected_key"] = "hacked"

    # Subsequent retrieval must be unaffected
    cfg2 = state.get_chat_config(-10042)
    assert cfg2["antispam_limit"] == 5
    assert "new_injected_key" not in cfg2


def test_bridge_state_get_command_scope_robust_input():
    """Verify get_command_scope handles None, non-string, @botname, casing, and empty input."""
    BridgeState = _get_bridge_state_class()
    state = BridgeState()

    state.update(
        runtime_config={
            "command_scopes": {
                "kryaken": "PRIVATE",
                "cmd_where_scope": "PUBLIC",
                "profile": "OFF",
            }
        },
        approved_chats=[],
    )

    # Edge cases for command input
    assert state.get_command_scope(None) == "all"  # type: ignore
    assert state.get_command_scope(12345) == "all"  # type: ignore
    assert state.get_command_scope("") == "all"
    assert state.get_command_scope("   ") == "all"

    # Command with @botname
    assert state.get_command_scope("/kryaken@school21_bot") == "PRIVATE"
    assert state.get_command_scope("where@school21_bot") == "PUBLIC"

    # Case insensitivity
    assert state.get_command_scope("KRYAKEN") == "PRIVATE"
    assert state.get_command_scope("/WHERE") == "PUBLIC"
    assert state.get_command_scope("/Profile@MyBot") == "OFF"

