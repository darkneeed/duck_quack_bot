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
    label = "✅ Одобрено" if decision == "approved" else "❌ Отклонено"
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


from ..strings import (  # noqa: E402
    CABINET_BTN_CARD,
    CABINET_BTN_PROFILE,
    CABINET_BTN_GENCODE,
    CABINET_BTN_MYCODES,
    CABINET_BTN_HELP,
    PEER_CARD_BTN_BACK,
    PEER_CARD_BTN_CANCEL,
    PEER_CARD_BTN_CONTACT,
    PEER_CARD_BTN_CONTACT_MAX,
    PEER_CARD_BTN_CONTACT_ROCKET,
    PEER_CARD_BTN_CONTACT_TG,
    PEER_CARD_BTN_DELETE_COMMENT,
    PEER_CARD_BTN_DELETE_PHOTO,
    PEER_CARD_BTN_EDIT_COMMENT,
    PEER_CARD_BTN_EDIT_PHOTO,
    PEER_CARD_SUBMISSION_BTN_APPROVE,
    PEER_CARD_SUBMISSION_BTN_REJECT,
    PEER_CARD_SUBMISSION_REASON_COMMENT_PERSONAL,
    PEER_CARD_SUBMISSION_REASON_COMMENT_RULES,
    PEER_CARD_SUBMISSION_REASON_COMMENT_SWEAR,
    PEER_CARD_SUBMISSION_REASON_PHOTO_FACE,
    PEER_CARD_SUBMISSION_REASON_PHOTO_OTHERS,
)


def cabinet_home_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Main menu for approved users."""
    builder = InlineKeyboardBuilder()
    builder.button(text=CABINET_BTN_PROFILE, callback_data="cabinet:profile")
    builder.button(text=CABINET_BTN_CARD, callback_data="cabinet:card_open")
    builder.button(text=CABINET_BTN_GENCODE, callback_data="cabinet:gencode")
    builder.button(text=CABINET_BTN_MYCODES, callback_data="cabinet:mycodes")
    builder.button(text=CABINET_BTN_HELP, callback_data="cabinet:help")
    if is_admin:
        builder.button(text="🛠 Админ-панель", callback_data="cabinet:admin_panel")
    builder.adjust(1)
    return builder.as_markup()


def cabinet_back_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="cabinet:home"))
    if is_admin:
        builder.row(InlineKeyboardButton(text="🛠 Админ-панель", callback_data="cabinet:admin_panel"))
    return builder.as_markup()


def cabinet_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    return cabinet_home_kb(is_admin=is_admin)


def cabinet_profile_card_kb(*, has_photo: bool, has_comment: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=PEER_CARD_BTN_EDIT_PHOTO, callback_data="cabinet:card_edit_photo")
    builder.button(text=PEER_CARD_BTN_EDIT_COMMENT, callback_data="cabinet:card_edit_comment")
    builder.button(text=PEER_CARD_BTN_CONTACT, callback_data="cabinet:card_contact")
    if has_photo:
        builder.button(text=PEER_CARD_BTN_DELETE_PHOTO, callback_data="cabinet:card_delete_photo")
    if has_comment:
        builder.button(text=PEER_CARD_BTN_DELETE_COMMENT, callback_data="cabinet:card_delete_comment")
    builder.button(text=PEER_CARD_BTN_BACK, callback_data="cabinet:card_back")
    builder.adjust(1)
    return builder.as_markup()


def cabinet_profile_card_contact_kb(selected: str) -> InlineKeyboardMarkup:
    labels = {
        "tg": PEER_CARD_BTN_CONTACT_TG,
        "max": PEER_CARD_BTN_CONTACT_MAX,
        "rocket": PEER_CARD_BTN_CONTACT_ROCKET,
    }
    builder = InlineKeyboardBuilder()
    for value in ("tg", "max", "rocket"):
        prefix = "✅ " if selected == value else ""
        builder.button(
            text=f"{prefix}{labels[value]}",
            callback_data=f"cabinet:card_contact_set:{value}",
        )
    builder.button(text=PEER_CARD_BTN_BACK, callback_data="cabinet:card_refresh")
    builder.adjust(1)
    return builder.as_markup()


def cabinet_cancel_input_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=PEER_CARD_BTN_CANCEL, callback_data="cabinet:card_cancel_input"))
    return builder.as_markup()


def profile_card_submission_kb(*, submission_type: str, tg_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=PEER_CARD_SUBMISSION_BTN_APPROVE,
            callback_data=f"profile_card:approve:{submission_type}:{tg_id}",
        ),
        InlineKeyboardButton(
            text=PEER_CARD_SUBMISSION_BTN_REJECT,
            callback_data=f"profile_card:reject:{submission_type}:{tg_id}",
        ),
    )
    return builder.as_markup()


def profile_card_reject_reason_kb(*, submission_type: str, tg_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if submission_type == "photo":
        builder.row(
            InlineKeyboardButton(
                text=PEER_CARD_SUBMISSION_REASON_PHOTO_FACE,
                callback_data=f"profile_card:reject_reason:{submission_type}:{tg_id}:no_face",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=PEER_CARD_SUBMISSION_REASON_PHOTO_OTHERS,
                callback_data=f"profile_card:reject_reason:{submission_type}:{tg_id}:has_others",
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=PEER_CARD_SUBMISSION_REASON_COMMENT_SWEAR,
                callback_data=f"profile_card:reject_reason:{submission_type}:{tg_id}:swear",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=PEER_CARD_SUBMISSION_REASON_COMMENT_RULES,
                callback_data=f"profile_card:reject_reason:{submission_type}:{tg_id}:rules",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=PEER_CARD_SUBMISSION_REASON_COMMENT_PERSONAL,
                callback_data=f"profile_card:reject_reason:{submission_type}:{tg_id}:personal",
            )
        )
    return builder.as_markup()
