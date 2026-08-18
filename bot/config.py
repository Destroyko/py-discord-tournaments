import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    pass


def _get_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"Переменная окружения {name} обязательна и не задана.")
    return value


def _get_int(name: str) -> int:
    value = _get_required(name)
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(
            f"Переменная окружения {name} должна быть числом (id), получено: {value!r}"
        ) from exc


def _get_int_list(name: str) -> List[int]:
    value = _get_required(name)
    ids: List[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError as exc:
            raise ConfigError(
                f"Переменная окружения {name} должна содержать id через запятую, получено: {value!r}"
            ) from exc
    if not ids:
        raise ConfigError(f"Переменная окружения {name} не содержит ни одного id.")
    return ids


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    discord_token: str
    guild_id: int
    setup_channel_id: int
    registration_channel_id: int
    notification_channel_id: int
    manager_role_ids: List[int]
    participant_role_id: int
    post_to_channel_enabled: bool
    db_path: str


def load_config() -> Config:
    load_dotenv()
    return Config(
        discord_token=_get_required("DISCORD_TOKEN"),
        guild_id=_get_int("GUILD_ID"),
        setup_channel_id=_get_int("SETUP_CHANNEL_ID"),
        registration_channel_id=_get_int("REGISTRATION_CHANNEL_ID"),
        notification_channel_id=_get_int("NOTIFICATION_CHANNEL_ID"),
        manager_role_ids=_get_int_list("MANAGER_ROLE_IDS"),
        participant_role_id=_get_int("PARTICIPANT_ROLE_ID"),
        post_to_channel_enabled=_get_bool("POST_TO_CHANNEL_ENABLED", default=True),
        db_path=os.getenv("DB_PATH", "tournaments.db"),
    )
