from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def moderation_card_kb(app_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{app_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{app_id}"),
    )
    return builder.as_markup()


def skip_comment_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_comment"))
    return builder.as_markup()


def reject_reason_input_kb(app_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🚫 Не наш кампус", callback_data=f"reject_reason:{app_id}:campus"))
    builder.row(InlineKeyboardButton(text="👤 Не участник школы", callback_data=f"reject_reason:{app_id}:not_student"))
    builder.row(InlineKeyboardButton(text="⚠️ Подозрительная заявка", callback_data=f"reject_reason:{app_id}:suspicious"))
    builder.row(InlineKeyboardButton(text="⏭ Без причины", callback_data=f"reject_skip:{app_id}"))
    return builder.as_markup()


def cooldown_with_reason_kb(app_id: int, reason: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Нет", callback_data=f"cooldown:{app_id}:0"),
        InlineKeyboardButton(text="1ч", callback_data=f"cooldown:{app_id}:3600"),
        InlineKeyboardButton(text="24ч", callback_data=f"cooldown:{app_id}:86400"),
        InlineKeyboardButton(text="72ч", callback_data=f"cooldown:{app_id}:259200"),
    )
    return builder.as_markup()


def skip_reason_kb(app_id: int) -> InlineKeyboardMarkup:
    return reject_reason_input_kb(app_id)


def cooldown_kb(app_id: int) -> InlineKeyboardMarkup:
    return cooldown_with_reason_kb(app_id, None)


def decided_kb(decision: str, moderator_name: str = "") -> InlineKeyboardMarkup:
    _labels = {
        "approved":   "✅ Одобрено",
        "rejected":   "❌ Отклонено",
        "suspicious": "⚠️ Отмечено как подозрительное",
    }
    label = _labels.get(decision, decision)
    if moderator_name:
        label += f" · {moderator_name}"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=label, callback_data="noop"))
    return builder.as_markup()


def failed_auth_kb(tg_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🚫 Пропустить", callback_data=f"fail_skip:{tg_id}"),
        InlineKeyboardButton(text="🔨 Заблокировать", callback_data=f"fail_ban:{tg_id}"),
    )
    return builder.as_markup()


def ban_duration_kb(tg_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1ч", callback_data=f"fail_ban_do:{tg_id}:3600"),
        InlineKeyboardButton(text="24ч", callback_data=f"fail_ban_do:{tg_id}:86400"),
        InlineKeyboardButton(text="72ч", callback_data=f"fail_ban_do:{tg_id}:259200"),
        InlineKeyboardButton(text="Навсегда", callback_data=f"fail_ban_do:{tg_id}:0"),
    )
    return builder.as_markup()


def verification_request_kb(app_id: int, candidate_login: str) -> InlineKeyboardMarkup:
    """Three-button keyboard sent to teammate verifiers."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Подтвердить",          callback_data=f"verify:{app_id}:confirm"))
    builder.row(InlineKeyboardButton(text="❌ Не могу подтвердить",  callback_data=f"verify:{app_id}:decline"))
    builder.row(InlineKeyboardButton(text="⚠️ Выглядит странно",    callback_data=f"verify:{app_id}:suspicious"))
    return builder.as_markup()


def verification_result_kb(result: str, voter_name: str = "") -> InlineKeyboardMarkup:
    """Informational-only keyboard shown after social trust vote — no voting buttons."""
    icons  = {"confirm": "✅", "decline": "❌", "suspicious": "⚠️"}
    labels = {"confirm": "Подтверждено", "decline": "Не подтверждено", "suspicious": "Отмечено как странное"}
    icon  = icons.get(result, "ℹ️")
    label = labels.get(result, result)
    if voter_name:
        label += f" · {voter_name}"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"{icon} {label}", callback_data="noop"))
    return builder.as_markup()
