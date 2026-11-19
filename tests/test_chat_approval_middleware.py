from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest
from aiogram.types import CallbackQuery, Chat, Message, User


def _get_chat_approval_middleware_class():
    from s21_bot.middlewares.chat_approval import ChatApprovalMiddleware

    return ChatApprovalMiddleware


def _get_bridge_state_class():
    from s21_bot.services.bridge_state import BridgeState

    return BridgeState


def _make_message(chat_id: int, chat_type: str = "supergroup", text: str = "Hello world") -> Message:
    msg = MagicMock(spec=Message)
    msg.message_id = 42
    msg.text = text
    msg.chat = Chat(id=chat_id, type=chat_type, title=f"Chat {chat_id}")
    msg.from_user = User(id=999, is_bot=False, first_name="Student", username="student21")
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    msg.delete = AsyncMock()
    return msg


# ============================================================================
# ChatApprovalMiddleware Tests
# ============================================================================


@pytest.mark.asyncio
async def test_unapproved_group_chat_drops_event_completely_silent():
    """Case 1 (Unapproved chat): incoming Message in group where chat.id is NOT in

    approved_chats -> middleware drops event completely, does not invoke next handler.
    Bot is 100% silent.
    """
    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    # State has NO approved chats
    assert not state.is_chat_approved(-100999)

    middleware = ChatApprovalMiddleware(bridge_state=state)
    message = _make_message(chat_id=-100999, chat_type="group", text="Hello guys")
    next_handler = AsyncMock()
    data: dict = {}

    result = await middleware(next_handler, message, data)

    # Next handler MUST NOT be invoked
    assert not next_handler.called
    # Bot MUST be 100% silent: no answer, no reply, no delete
    assert not message.answer.called
    assert not message.reply.called
    assert not message.delete.called
    assert result is None


@pytest.mark.asyncio
async def test_unapproved_supergroup_chat_drops_event_completely_silent():
    """Verify silence in supergroup that is not approved."""
    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    middleware = ChatApprovalMiddleware(bridge_state=state)
    message = _make_message(chat_id=-100888777, chat_type="supergroup", text="Random message")
    next_handler = AsyncMock()

    result = await middleware(next_handler, message, {})

    assert not next_handler.called
    assert not message.answer.called
    assert result is None


@pytest.mark.asyncio
async def test_approved_group_chat_injects_config_and_invokes_handler():
    """Case 2 (Approved chat): incoming Message in group where chat.id IS in

    approved_chats -> middleware injects chat_config and invokes next handler.
    """
    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    expected_chat_config = {
        "welcome_message_enabled": True,
        "welcome_message_text": "Добро пожаловать в Школу 21!",
        "antispam_enabled": True,
        "antispam_limit": 5,
        "antispam_window_seconds": 5,
        "antispam_mute_minutes": 15,
        "filter_links_enabled": True,
        "auto_delete_join_messages": True,
    }

    state.update(
        runtime_config={},
        approved_chats=[
            {
                "tg_chat_id": -1001234567890,
                "title": "Волгоград Основной Чат",
                "chat_type": "supergroup",
                "config_json": expected_chat_config,
            }
        ],
    )

    middleware = ChatApprovalMiddleware(bridge_state=state)
    message = _make_message(chat_id=-1001234567890, chat_type="supergroup", text="Добрый день")
    next_handler = AsyncMock(return_value="handled_ok")
    data: dict = {"bot": MagicMock()}

    result = await middleware(next_handler, message, data)

    # Next handler MUST be invoked
    assert next_handler.called
    assert result == "handled_ok"

    # chat_config MUST be injected into data
    assert "chat_config" in data
    assert data["chat_config"] == expected_chat_config
    assert data["chat_config"]["antispam_enabled"] is True


@pytest.mark.asyncio
async def test_private_chat_allows_event_without_approval_check():
    """Case 3 (Private chat): user sends message in private chat -> middleware allows

    event without approval check.
    """
    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    # Private chat ID is NOT in approved_chats (and should never be required)
    private_chat_id = 555666777
    assert not state.is_chat_approved(private_chat_id)

    middleware = ChatApprovalMiddleware(bridge_state=state)
    message = _make_message(chat_id=private_chat_id, chat_type="private", text="/start")
    next_handler = AsyncMock(return_value="private_ok")
    data: dict = {}

    result = await middleware(next_handler, message, data)

    # Handler MUST be called for private chat
    assert next_handler.called
    assert result == "private_ok"


@pytest.mark.asyncio
async def test_chat_approval_revoked_ceases_moderation_immediately():
    """Case 4 (Chat approval revoked): chat transitioned from approved to rejected ->

    bot immediately ceases moderation.
    """
    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    chat_id = -1001234567890

    # Step 1: Chat is approved
    state.update(
        runtime_config={},
        approved_chats=[
            {
                "tg_chat_id": chat_id,
                "title": "Core Chat",
                "chat_type": "supergroup",
                "config_json": {"antispam_enabled": True},
            }
        ],
    )
    assert state.is_chat_approved(chat_id)

    middleware = ChatApprovalMiddleware(bridge_state=state)
    msg1 = _make_message(chat_id=chat_id, chat_type="supergroup", text="First message")
    handler1 = AsyncMock(return_value="resp1")

    res1 = await middleware(handler1, msg1, {})
    assert handler1.called
    assert res1 == "resp1"

    # Step 2: Chat approval is revoked (e.g. rejected by admin or auto-leave)
    state.update(
        runtime_config={},
        approved_chats=[],  # chat_id is now removed / rejected
    )
    assert not state.is_chat_approved(chat_id)

    # Step 3: Next message in the same chat MUST be dropped silently
    msg2 = _make_message(chat_id=chat_id, chat_type="supergroup", text="Second message after revoke")
    handler2 = AsyncMock()

    res2 = await middleware(handler2, msg2, {})
    assert not handler2.called
    assert not msg2.answer.called
    assert res2 is None


@pytest.mark.asyncio
async def test_multiple_chats_isolation():
    """Verify that approval of chat A does not allow messages in unapproved chat B."""
    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    approved_id = -100111
    unapproved_id = -100222

    state.update(
        runtime_config={},
        approved_chats=[
            {
                "tg_chat_id": approved_id,
                "title": "Approved",
                "chat_type": "supergroup",
                "config_json": {"welcome": True},
            }
        ],
    )

    middleware = ChatApprovalMiddleware(bridge_state=state)

    # Message in approved chat -> runs
    msg_a = _make_message(chat_id=approved_id, text="A")
    handler_a = AsyncMock(return_value="ok_a")
    res_a = await middleware(handler_a, msg_a, {})
    assert handler_a.called
    assert res_a == "ok_a"

    # Message in unapproved chat -> dropped
    msg_b = _make_message(chat_id=unapproved_id, text="B")
    handler_b = AsyncMock()
    res_b = await middleware(handler_b, msg_b, {})
    assert not handler_b.called
    assert res_b is None


@pytest.mark.asyncio
async def test_middleware_preserves_context_data():
    """Verify that existing keys in data dictionary are preserved when next handler is invoked."""
    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    chat_id = -100123
    state.update(
        runtime_config={},
        approved_chats=[{"tg_chat_id": chat_id, "title": "Chat", "config_json": {"rule": 1}}],
    )

    middleware = ChatApprovalMiddleware(bridge_state=state)
    message = _make_message(chat_id=chat_id, chat_type="supergroup")

    passed_data = None

    async def sample_handler(event, data):
        nonlocal passed_data
        passed_data = data
        return "done"

    initial_bot = MagicMock()
    initial_user = MagicMock()
    data = {
        "bot": initial_bot,
        "event_from_user": initial_user,
        "raw_state": "active",
    }

    await middleware(sample_handler, message, data)

    assert passed_data is not None
    assert passed_data["bot"] is initial_bot
    assert passed_data["event_from_user"] is initial_user
    assert passed_data["raw_state"] == "active"
    assert "chat_config" in passed_data
    assert passed_data["chat_config"] == {"rule": 1}


@pytest.mark.asyncio
async def test_chat_approval_middleware_allows_my_chat_member_event_unconditionally():
    """Verify that ChatMemberUpdated / my_chat_member updates always pass through

    even if the chat is not approved yet (required for bot to detect addition).
    """
    from aiogram.types import ChatMemberUpdated

    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    assert not state.is_chat_approved(-100999)

    middleware = ChatApprovalMiddleware(bridge_state=state)
    chat_member_update = MagicMock(spec=ChatMemberUpdated)
    chat_member_update.chat = Chat(id=-100999, type="supergroup")

    handler = AsyncMock(return_value="member_updated_ok")
    data: dict = {}

    res = await middleware(handler, chat_member_update, data)
    assert handler.called
    assert res == "member_updated_ok"


@pytest.mark.asyncio
async def test_chat_approval_middleware_channel_chat_moderation():
    """Verify that channel chats are subject to approval rules just like groups."""
    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    approved_channel_id = -100444
    unapproved_channel_id = -100555

    state.update(
        runtime_config={},
        approved_chats=[
            {
                "tg_chat_id": approved_channel_id,
                "title": "News Channel",
                "chat_type": "channel",
                "config_json": {"channel_mode": True},
            }
        ],
    )

    middleware = ChatApprovalMiddleware(bridge_state=state)

    # Approved channel -> passes
    msg_approved = _make_message(chat_id=approved_channel_id, chat_type="channel")
    handler_a = AsyncMock(return_value="channel_ok")
    data_a: dict = {}
    res_a = await middleware(handler_a, msg_approved, data_a)
    assert handler_a.called
    assert res_a == "channel_ok"
    assert data_a["chat_config"] == {"channel_mode": True}

    # Unapproved channel -> drops
    msg_unapproved = _make_message(chat_id=unapproved_channel_id, chat_type="channel")
    handler_b = AsyncMock()
    res_b = await middleware(handler_b, msg_unapproved, {})
    assert not handler_b.called
    assert res_b is None


@pytest.mark.asyncio
async def test_chat_approval_middleware_event_without_chat_passes():
    """Verify that non-chat events (e.g. inline query or chosen inline) pass through safely."""
    from aiogram.types import TelegramObject

    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    middleware = ChatApprovalMiddleware(bridge_state=state)

    arbitrary_event = MagicMock(spec=TelegramObject)
    # Remove chat / message attributes
    del arbitrary_event.chat
    del arbitrary_event.message
    del arbitrary_event.my_chat_member

    handler = AsyncMock(return_value="pass_through")
    data: dict = {}

    res = await middleware(handler, arbitrary_event, data)
    assert handler.called
    assert res == "pass_through"


@pytest.mark.asyncio
async def test_chat_approval_middleware_callback_query_unapproved_chat_silent():
    """Verify that CallbackQuery in an unapproved group chat is dropped silently."""
    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    middleware = ChatApprovalMiddleware(bridge_state=state)

    cq = MagicMock(spec=CallbackQuery)
    cq.message = _make_message(chat_id=-100999, chat_type="supergroup")
    cq.answer = AsyncMock()

    handler = AsyncMock()
    data: dict = {}

    res = await middleware(handler, cq, data)
    assert not handler.called
    assert not cq.answer.called
    assert res is None


@pytest.mark.asyncio
async def test_chat_approval_middleware_callback_query_approved_chat_allows():
    """Verify that CallbackQuery in an approved chat injects config and invokes handler."""
    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    state.update(
        runtime_config={},
        approved_chats=[
            {
                "tg_chat_id": -100123,
                "title": "Approved Group",
                "config_json": {"antispam_limit": 10},
            }
        ],
    )
    middleware = ChatApprovalMiddleware(bridge_state=state)

    cq = MagicMock(spec=CallbackQuery)
    cq.message = _make_message(chat_id=-100123, chat_type="supergroup")
    cq.answer = AsyncMock()

    handler = AsyncMock(return_value="cq_handled")
    data: dict = {}

    res = await middleware(handler, cq, data)
    assert handler.called
    assert data.get("chat_config") == {"antispam_limit": 10}
    assert res == "cq_handled"


@pytest.mark.asyncio
async def test_chat_approval_middleware_exempts_moderation_and_community_chats():
    """Verify that CallbackQuery and Message in moderation and community chats
    are always permitted even if they are NOT in bridge_state.approved_chats.
    This fixes the bug where moderator approve/reject buttons stopped responding.
    """
    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    # Ensure moderation chat and community chat are NOT in approved_chats
    mod_chat_id = -1003838404773
    comm_chat_id = -1003864598898
    assert not state.is_chat_approved(mod_chat_id)
    assert not state.is_chat_approved(comm_chat_id)

    mock_config = MagicMock()
    mock_config.moderation_chat_id = mod_chat_id
    mock_config.community_chat_id = comm_chat_id
    mock_config.events_chat_id = 0

    middleware = ChatApprovalMiddleware(bridge_state=state)

    # 1. Callback query on moderation card in moderation chat
    cq = MagicMock(spec=CallbackQuery)
    cq.message = _make_message(chat_id=mod_chat_id, chat_type="supergroup")
    cq.answer = AsyncMock()

    handler = AsyncMock(return_value="moderation_action_ok")
    data = {"config": mock_config}

    res = await middleware(handler, cq, data)
    assert handler.called
    assert res == "moderation_action_ok"

    # 2. Message in moderation chat
    msg = _make_message(chat_id=mod_chat_id, chat_type="supergroup", text="/approve 208")
    handler2 = AsyncMock(return_value="msg_ok")
    res2 = await middleware(handler2, msg, data)
    assert handler2.called
    assert res2 == "msg_ok"

    # 3. Callback query in community chat
    cq_comm = MagicMock(spec=CallbackQuery)
    cq_comm.message = _make_message(chat_id=comm_chat_id, chat_type="supergroup")
    handler3 = AsyncMock(return_value="community_action_ok")
    res3 = await middleware(handler3, cq_comm, data)
    assert handler3.called
    assert res3 == "community_action_ok"


@pytest.mark.asyncio
async def test_chat_approval_middleware_exempts_system_chat_ids_param():
    """Verify that system_chat_ids passed directly in constructor are exempt."""
    ChatApprovalMiddleware = _get_chat_approval_middleware_class()
    BridgeState = _get_bridge_state_class()

    state = BridgeState()
    system_chat_id = -100987654321
    middleware = ChatApprovalMiddleware(bridge_state=state, system_chat_ids={system_chat_id})

    msg = _make_message(chat_id=system_chat_id, chat_type="supergroup", text="Hello system")
    handler = AsyncMock(return_value="system_chat_ok")
    data: dict = {}

    res = await middleware(handler, msg, data)
    assert handler.called
    assert res == "system_chat_ok"


