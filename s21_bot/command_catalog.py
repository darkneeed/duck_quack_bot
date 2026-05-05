from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Iterable

from .config import Config


@dataclass(frozen=True)
class CommandSpec:
    command: str
    aliases: tuple[str, ...]
    description: str
    role: str
    group: str
    scope_key: str | None = None
    available_in_private: bool = False
    available_in_public: bool = False


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        command="/start",
        aliases=(),
        description="главное меню и запуск/повторный старт заявки",
        role="approved",
        group="private",
        available_in_private=True,
    ),
    CommandSpec(
        command="/invite <код>",
        aliases=(),
        description="применить инвайт-код к текущей заявке",
        role="approved",
        group="private",
        available_in_private=True,
    ),
    CommandSpec(
        command="/changetg",
        aliases=(),
        description="подсказка по смене Telegram-аккаунта",
        role="approved",
        group="private",
        available_in_private=True,
    ),
    CommandSpec(
        command="/profile",
        aliases=(),
        description="показать профиль на платформе",
        role="approved",
        group="scoped",
        scope_key="cmd_profile_scope",
        available_in_private=True,
        available_in_public=True,
    ),
    CommandSpec(
        command="/where <логин>",
        aliases=(),
        description="показать, где участник сидит в кампусе",
        role="approved",
        group="scoped",
        scope_key="cmd_where_scope",
        available_in_private=True,
        available_in_public=True,
    ),
    CommandSpec(
        command="/peers <проект>",
        aliases=("/пиры <проект>",),
        description="найти участников, которые сейчас делают проект",
        role="approved",
        group="scoped",
        scope_key="cmd_peers_scope",
        available_in_private=True,
        available_in_public=True,
    ),
    CommandSpec(
        command="/logtime [логин]",
        aliases=("/логтайм [логин]",),
        description="посмотреть среднее время в кампусе за неделю",
        role="approved",
        group="scoped",
        scope_key="cmd_logtime_scope",
        available_in_private=True,
        available_in_public=True,
    ),
    CommandSpec(
        command="/top",
        aliases=("/топ",),
        description="показать топ участников по XP",
        role="approved",
        group="scoped",
        scope_key="cmd_top_scope",
        available_in_private=True,
        available_in_public=True,
    ),
    CommandSpec(
        command="/incampus",
        aliases=("/вкампусе",),
        description="показать, кто из участников сейчас в кампусе",
        role="approved",
        group="scoped",
        scope_key="cmd_incampus_scope",
        available_in_private=True,
        available_in_public=True,
    ),
    CommandSpec(
        command="/events",
        aliases=("/мероприятия",),
        description="показать ближайшие мероприятия кампуса",
        role="approved",
        group="scoped",
        scope_key="cmd_events_scope",
        available_in_private=True,
        available_in_public=True,
    ),
    CommandSpec(
        command="/alarm",
        aliases=("/алярм",),
        description="ответом на сообщение вызвать модераторов",
        role="approved",
        group="community",
        available_in_public=True,
    ),
    CommandSpec(
        command="/ban <id> [причина]",
        aliases=("/бан <id> [причина]",),
        description="забанить пользователя в чате сообщества",
        role="moderator",
        group="community_mod",
        available_in_public=True,
    ),
    CommandSpec(
        command="/mute <id> <минуты> [причина]",
        aliases=("/мут <id> <минуты> [причина]",),
        description="замутить пользователя в чате сообщества",
        role="moderator",
        group="community_mod",
        available_in_public=True,
    ),
    CommandSpec(
        command="/unmute <id>",
        aliases=("/анмут <id>",),
        description="снять мут в чате сообщества",
        role="moderator",
        group="community_mod",
        available_in_public=True,
    ),
    CommandSpec(
        command="/unban <id>",
        aliases=("/разбан <id>",),
        description="разбанить пользователя в чате сообщества",
        role="moderator",
        group="community_mod",
        available_in_public=True,
    ),
    CommandSpec(
        command="/delete",
        aliases=("/удалить",),
        description="ответом удалить сообщение в чате сообщества",
        role="moderator",
        group="community_mod",
        available_in_public=True,
    ),
    CommandSpec(
        command="/antispam ...",
        aliases=("/антиспам ...",),
        description="посмотреть статус или изменить настройки антиспама",
        role="moderator",
        group="community_mod",
        available_in_public=True,
    ),
    CommandSpec(
        command="/ban <id> [причина]",
        aliases=(),
        description="заблокировать пользователя в базе",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/unban <id>",
        aliases=(),
        description="снять блокировку в базе",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/userinfo <id>",
        aliases=(),
        description="показать карточку пользователя из базы",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/history <id>",
        aliases=(),
        description="история попыток авторизации пользователя",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/approve <app_id>",
        aliases=(),
        description="одобрить заявку вручную",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/deluser <id>",
        aliases=(),
        description="удалить пользователя и его заявки из базы",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/cleardb",
        aliases=(),
        description="полностью очистить базу",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/events",
        aliases=(),
        description="ближайшие мероприятия для модераторов",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/guestinvite <tg_id> <логин>",
        aliases=("/гостьинвайт <tg_id> <логин>",),
        description="создать гостевой инвайт для участника другого кампуса",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/dm <id|логин> <текст>",
        aliases=("/написать <id|логин> <текст>",),
        description="отправить личное сообщение пользователю",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/gencode",
        aliases=(),
        description="создать одноразовый инвайт-код с QR",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/mycodes",
        aliases=(),
        description="показать созданные вами инвайт-коды",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/export",
        aliases=(),
        description="выгрузить базу в CSV",
        role="moderator",
        group="moderation",
        available_in_public=True,
    ),
    CommandSpec(
        command="/exportdebug",
        aliases=(),
        description="отладочная выгрузка экспорта",
        role="moderator",
        group="other",
        available_in_private=True,
        available_in_public=True,
    ),
    CommandSpec(
        command="/admin",
        aliases=(),
        description="открыть админ-панель runtime-настроек",
        role="admin",
        group="admin_private",
        available_in_private=True,
    ),
    CommandSpec(
        command="/post",
        aliases=("/пост",),
        description="опубликовать пост в общий чат/топик",
        role="admin",
        group="admin_private",
        available_in_private=True,
    ),
)


GROUP_TITLES: dict[str, str] = {
    "private": "Личка бота",
    "scoped": "Команды участников со scope-настройкой",
    "community": "Чат сообщества",
    "community_mod": "Модерация в чате сообщества",
    "moderation": "Чат модерации",
    "admin_private": "Админская личка",
    "other": "Прочее",
}


ROLE_LABELS: dict[str, str] = {
    "approved": "Участник",
    "moderator": "Модератор",
    "admin": "Админ",
}


def _scope_allows(scope: str, chat_type: str) -> bool:
    is_private = chat_type == "private"
    if scope == "PRIVATE":
        return is_private
    if scope == "PUBLIC":
        return not is_private
    if scope == "OFF":
        return False
    return True


def _is_visible_in_chat(spec: CommandSpec, config: Config, chat_type: str) -> bool:
    if spec.scope_key:
        return _scope_allows(getattr(config, spec.scope_key), chat_type)
    if chat_type == "private":
        return spec.available_in_private
    return spec.available_in_public


def get_visible_commands(
    config: Config,
    *,
    role: str,
    chat_type: str,
) -> list[CommandSpec]:
    return [
        spec
        for spec in COMMAND_SPECS
        if spec.role == role and _is_visible_in_chat(spec, config, chat_type)
    ]


def render_approved_short_help(config: Config) -> str:
    commands = get_visible_commands(config, role="approved", chat_type="private")
    lines = ["💡 <b>Что можно сделать дальше</b>\n"]
    for spec in commands[:6]:
        lines.append(f"<code>{html.escape(spec.command)}</code> — {spec.description}")
    return "\n".join(lines)


def render_cabinet_help(config: Config) -> str:
    commands = get_visible_commands(config, role="approved", chat_type="private")
    lines = ["📖 <b>Команды, доступные здесь</b>\n"]
    for spec in commands:
        lines.append(f"<code>{html.escape(spec.command)}</code> — {spec.description}")
        for alias in spec.aliases:
            lines.append(f"<code>{html.escape(alias)}</code> — то же самое")
    return "\n".join(lines)


def _aliases_text(aliases: Iterable[str]) -> str:
    items = tuple(aliases)
    return ", ".join(items) if items else "—"


def _availability_text(spec: CommandSpec) -> str:
    if spec.scope_key:
        return f"scope: <code>{spec.scope_key}</code>"
    labels: list[str] = []
    if spec.available_in_private:
        labels.append("private")
    if spec.available_in_public:
        labels.append("public")
    return ", ".join(labels) if labels else "—"


def render_commands_markdown() -> str:
    lines = [
        "# Команды бота",
        "",
        "> Этот файл синхронизирован с каталогом `s21_bot/command_catalog.py`.",
        "",
        "Ниже перечислены реальные команды и алиасы, разбитые по контексту использования.",
        "",
    ]

    for group in GROUP_TITLES:
        specs = [spec for spec in COMMAND_SPECS if spec.group == group]
        if not specs:
            continue
        lines.append(f"## {GROUP_TITLES[group]}")
        lines.append("")
        lines.append("| Команда | Алиасы | Кому | Описание | Где работает |")
        lines.append("|---------|--------|------|----------|--------------|")
        for spec in specs:
            lines.append(
                "| "
                f"`{spec.command}` | "
                f"{_aliases_text(f'`{alias}`' for alias in spec.aliases)} | "
                f"{ROLE_LABELS[spec.role]} | "
                f"{spec.description} | "
                f"{_availability_text(spec)} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Примечания",
            "",
            "- Для scope-команд доступность задаётся runtime-настройками `CMD_*_SCOPE` через `/admin`.",
            "- Команды модерации в чате сообщества работают только у модераторов/админов.",
            "- Команды в личке бота, требующие статус участника, доступны только после одобрения заявки.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_commands_markdown())
