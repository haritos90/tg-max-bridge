"""Telegram and Max clients with one common inbound shape."""

import logging
from dataclasses import dataclass

from .http import JsonClient

log = logging.getLogger(__name__)

TG = "tg"
MAX = "max"
LABELS = {TG: "Telegram", MAX: "Max"}

POLL_TIMEOUT = 30  # seconds the API holds an empty poll open


@dataclass
class Inbound:
    """One event from a private chat, normalized."""

    messenger: str
    user_id: int
    text: str | None
    has_attachments: bool = False
    username: str | None = None
    name: str = ""
    started: bool = False  # Start pressed, no message body
    callback: str | None = None  # button payload
    callback_id: str | None = None
    message_id: int | None = None  # message carrying the button


class Telegram:
    """Bot API over getUpdates long polling."""

    name = TG

    def __init__(self, token, api_url="https://api.telegram.org"):
        self.client = JsonClient("%s/bot%s" % (api_url, token))
        self.offset = None

    def whoami(self):
        return self.client.get("/getMe")["result"]

    def poll(self):
        params = {"timeout": POLL_TIMEOUT, "offset": self.offset,
                  "allowed_updates": '["message","callback_query"]'}
        data = self.client.get("/getUpdates", params, timeout=POLL_TIMEOUT + 30)
        events = []
        for upd in data.get("result", []):
            self.offset = upd["update_id"] + 1
            event = parse_telegram(upd)
            if event:
                events.append(event)
        return events

    def set_commands(self, commands, user_id=None):
        """commands: (name, description) pairs; user_id scopes them to one chat."""
        body = {"commands": [{"command": n, "description": d} for n, d in commands]}
        if user_id is not None:
            body["scope"] = {"type": "chat", "chat_id": user_id}
        self.client.post("/setMyCommands", body)

    def send(self, user_id, text, buttons=None):
        """buttons: rows of (label, payload); returns the message id."""
        body = {"chat_id": user_id, "text": text}
        if buttons:
            body["reply_markup"] = {"inline_keyboard": [
                [{"text": label, "callback_data": data} for label, data in row]
                for row in buttons]}
        return self.client.post("/sendMessage", body)["result"]["message_id"]

    def answer(self, ev, text, outcome=None):
        """Acknowledge a button press; outcome replaces the message text."""
        self.client.post("/answerCallbackQuery",
                         {"callback_query_id": ev.callback_id, "text": text})
        if outcome is not None and ev.message_id is not None:
            self.client.post("/editMessageText", {
                "chat_id": ev.user_id, "message_id": ev.message_id, "text": outcome})


def parse_telegram(upd):
    cq = upd.get("callback_query")
    if cq:
        sender = cq.get("from") or {}
        msg = cq.get("message") or {}
        return Inbound(TG, sender["id"], None, username=sender.get("username"),
                       callback=cq.get("data"), callback_id=cq.get("id"),
                       message_id=msg.get("message_id"))
    msg = upd.get("message") or {}
    chat = msg.get("chat") or {}
    sender = msg.get("from") or {}
    if chat.get("type") != "private" or not sender or sender.get("is_bot"):
        return None
    text = msg.get("text")
    name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")]))
    return Inbound(
        messenger=TG,
        user_id=sender["id"],
        text=None if text == "/start" else text,
        has_attachments=text is None,
        username=sender.get("username"),
        name=name,
        started=text == "/start",
    )


class Max:
    """Platform API over /updates long polling."""

    name = MAX

    def __init__(self, token, api_url="https://platform-api2.max.ru", ca_file=None):
        # Token goes in the header; query auth is gone.
        self.client = JsonClient(api_url, {"Authorization": token}, ca_file)
        self.marker = None

    def whoami(self):
        return self.client.get("/me")

    def poll(self):
        params = {"timeout": POLL_TIMEOUT, "marker": self.marker,
                  "types": "message_created,bot_started"}
        data = self.client.get("/updates", params, timeout=POLL_TIMEOUT + 30)
        self.marker = data.get("marker", self.marker)
        events = []
        for upd in data.get("updates", []):
            event = parse_max(upd)
            if event:
                events.append(event)
        return events

    def set_commands(self, commands, user_id=None):
        # Max has no per-chat scope; the menu is global.
        if user_id is not None:
            return
        self.client.patch("/me/commands", {"commands": [
            {"name": n, "description": d} for n, d in commands]})

    def send(self, user_id, text, buttons=None):
        # Buttons are a Telegram-side feature for now.
        self.client.post("/messages", {"text": text}, {"user_id": user_id})

    def answer(self, ev, text, outcome=None):
        pass


def parse_max(upd):
    kind = upd.get("update_type")
    if kind == "bot_started":
        user = upd.get("user") or {}
        return Inbound(MAX, user["user_id"], None, username=user.get("username"),
                       name=_max_name(user), started=True)
    if kind != "message_created":
        return None
    msg = upd.get("message") or {}
    user = msg.get("sender") or {}
    if (msg.get("recipient") or {}).get("chat_type") != "dialog" or not user:
        return None
    body = msg.get("body") or {}
    text = body.get("text") or None
    return Inbound(
        messenger=MAX,
        user_id=user["user_id"],
        text=None if text == "/start" else text,
        has_attachments=bool(body.get("attachments")),
        username=user.get("username"),
        name=_max_name(user),
        started=text == "/start",
    )


def _max_name(user):
    return " ".join(filter(None, [user.get("first_name"), user.get("last_name")]))
