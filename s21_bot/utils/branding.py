from __future__ import annotations

from ..config import Config
from ..strings import INVITE_MESSAGE_TEMPLATE, START_WELCOME


def build_profile_url(login: str, config: Config) -> str:
    return f"{config.platform_base_url.rstrip('/')}/profile/{login}"


def format_start_welcome(config: Config) -> str:
    return START_WELCOME.format(rules_url=config.rules_url)


def format_invite_message(invite_link: str, config: Config) -> str:
    return INVITE_MESSAGE_TEMPLATE.format(
        invite_link=invite_link,
        rules_url=config.rules_url,
        community_name=config.community_name,
        community_city=config.community_city,
    )
