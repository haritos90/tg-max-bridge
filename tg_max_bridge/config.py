"""Configuration from environment variables."""

import os
from dataclasses import dataclass, field

from .messengers import MAX, TG


class ConfigError(Exception):
    pass


@dataclass
class Config:
    tg_token: str
    max_token: str
    # Configured slots win over the state file.
    fixed: dict = field(default_factory=dict)  # (messenger, slot) -> id
    # Telegram usernames bound on first message, slot -> name.
    tg_usernames: dict = field(default_factory=dict)
    max_api_url: str = "https://platform-api2.max.ru"
    max_ca_file: str | None = None
    state_file: str = ""
    log_level: str = "INFO"


def _int(env, key):
    value = env.get(key, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise ConfigError("%s must be a number, got %r" % (key, value)) from None


def default_state_file(env):
    base = env.get("XDG_STATE_HOME") or os.path.join(
        env.get("HOME", "."), ".local", "state")
    return os.path.join(base, "tg-max-bridge", "state.json")


def load(env=None):
    env = os.environ if env is None else env
    missing = [k for k in ("TG_BOT_TOKEN", "MAX_BOT_TOKEN") if not env.get(k, "").strip()]
    # task-4: TG_ADMIN_ID stays as an alias.
    if not (env.get("TG_ADMIN", "").strip() or env.get("TG_ADMIN_ID", "").strip()):
        missing.append("TG_ADMIN")
    if missing:
        raise ConfigError("missing: " + ", ".join(missing))
    cfg = Config(
        tg_token=env["TG_BOT_TOKEN"].strip(),
        max_token=env["MAX_BOT_TOKEN"].strip(),
        max_api_url=env.get("MAX_API_URL", "").strip() or Config.max_api_url,
        max_ca_file=env.get("MAX_CA_FILE", "").strip() or None,
        state_file=env.get("STATE_FILE", "").strip() or default_state_file(env),
        log_level=env.get("LOG_LEVEL", "").strip() or "INFO",
    )
    # Each Telegram slot is a numeric id or a username.
    for slot, keys in ((1, ("TG_ADMIN", "TG_ADMIN_ID")), (2, ("TG_USER_2",))):
        value = ""
        for key in keys:
            value = value or env.get(key, "").strip().lstrip("@")
        if value.isdigit():
            cfg.fixed[(TG, slot)] = int(value)
        elif value:
            cfg.tg_usernames[slot] = value.lower()
    for slot in (1, 2):
        value = _int(env, "MAX_USER_%d" % slot)
        if value is not None:
            cfg.fixed[(MAX, slot)] = value
    return cfg
