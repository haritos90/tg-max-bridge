"""Telegram and Max clients with one common inbound shape."""

import logging
import mimetypes
import os
import time
import urllib.parse
from dataclasses import dataclass, field

from .http import HttpError, JsonClient

log = logging.getLogger(__name__)

TG = "tg"
MAX = "max"
LABELS = {TG: "Telegram", MAX: "Max"}

POLL_TIMEOUT = 30  # seconds the API holds an empty poll open
IMAGE = "image"
AUDIO = "audio"
CAPTION_MAX = 1000  # Telegram caps captions at 1024 UTF-16 units


@dataclass
class Media:
    """One relayable attachment: a picture or an audio message."""

    kind: str  # IMAGE or AUDIO
    ref: str  # file id on Telegram, download URL on Max


@dataclass
class Inbound:
    """One event from a private chat, normalized."""

    messenger: str
    user_id: int
    text: str | None
    has_attachments: bool = False  # content the bridge does not relay
    username: str | None = None
    name: str = ""
    started: bool = False  # Start pressed, no message body
    callback: str | None = None  # button payload
    callback_id: str | None = None
    message_id: int | None = None  # message carrying the button
    media: list = field(default_factory=list)  # Media items


def guess_mime(filename, fallback="application/octet-stream"):
    return mimetypes.guess_type(filename)[0] or fallback


class Telegram:
    """Bot API over getUpdates long polling."""

    name = TG

    def __init__(self, token, api_url="https://api.telegram.org"):
        self.client = JsonClient("%s/bot%s" % (api_url, token))
        self.file_base = "%s/file/bot%s/" % (api_url, token)
        self.offset = None

    def whoami(self):
        return self.client.get("/getMe")["result"]

    def set_commands(self, commands, user_id=None):
        """commands: (name, description) pairs; user_id scopes them to one chat."""
        body = {"commands": [{"command": n, "description": d} for n, d in commands]}
        if user_id is not None:
            body["scope"] = {"type": "chat", "chat_id": user_id}
        self.client.post("/setMyCommands", body)

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

    def send(self, user_id, text, buttons=None):
        """buttons: rows of (label, payload); returns the message id."""
        body = {"chat_id": user_id, "text": text,
                "link_preview_options": {"is_disabled": True}}
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

    def download(self, media):
        """(bytes, filename, mime) of a file id."""
        path = self.client.get("/getFile", {"file_id": media.ref})["result"]["file_path"]
        data, _ = self.client.get_bytes(self.file_base + path)
        filename = os.path.basename(path)
        return data, filename, guess_mime(filename)

    def send_media(self, user_id, kind, data, filename, mime, caption=None):
        if kind == IMAGE:
            method, name = "/sendPhoto", "photo"
        elif "ogg" in mime or "opus" in mime:
            method, name = "/sendVoice", "voice"  # voice bubble needs OGG Opus
        else:
            method, name = "/sendAudio", "audio"
        self.client.post_multipart(method, {"chat_id": user_id, "caption": caption},
                                   name, filename, data, mime)


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
    media = []
    if msg.get("photo"):
        media.append(Media(IMAGE, msg["photo"][-1]["file_id"]))  # largest size last
    for key in ("voice", "audio"):
        if msg.get(key):
            media.append(Media(AUDIO, msg[key]["file_id"]))
    other = {"document", "video", "video_note", "animation", "sticker",
             "location", "contact", "poll"}
    name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")]))
    return Inbound(
        messenger=TG,
        user_id=sender["id"],
        text=None if text == "/start" else (text or msg.get("caption")),
        has_attachments=bool(other & msg.keys()),
        username=sender.get("username"),
        name=name,
        started=text == "/start",
        media=media,
    )


class Max:
    """Platform API over /updates long polling."""

    name = MAX
    UPLOAD_RETRIES = (1, 2, 3, 5)  # seconds between send attempts while processing

    def __init__(self, token, api_url="https://platform-api2.max.ru", ca_file=None):
        # Token goes in the header; query auth is gone.
        self.client = JsonClient(api_url, {"Authorization": token}, ca_file)
        self.marker = None

    def whoami(self):
        return self.client.get("/me")

    def set_commands(self, commands, user_id=None):
        # Max has no per-chat scope; the menu is global.
        if user_id is not None:
            return
        self.client.patch("/me/commands", {"commands": [
            {"name": n, "description": d} for n, d in commands]})

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

    def send(self, user_id, text, buttons=None):
        # Buttons are a Telegram-side feature for now.
        self._send(user_id, {"text": text})

    def _send(self, user_id, body):
        self.client.post("/messages", body,
                         {"user_id": user_id, "disable_link_preview": "true"})

    def answer(self, ev, text, outcome=None):
        pass

    def download(self, media):
        data, content_type = self.client.get_bytes(media.ref)
        filename = os.path.basename(urllib.parse.urlparse(media.ref).path) or "file"
        mime = content_type.split(";")[0].strip() or guess_mime(filename)
        if "." not in filename:
            filename += mimetypes.guess_extension(mime) or ""
        return data, filename, mime

    def send_media(self, user_id, kind, data, filename, mime, caption=None):
        """Three steps: upload URL, upload, send; retry while processed."""
        endpoint = self.client.post("/uploads", None, {"type": kind})
        result = self.client.post_multipart(endpoint["url"], {}, "data", filename, data, mime)
        if kind == IMAGE:
            payload = {"photos": result.get("photos")}
        else:
            payload = {"token": endpoint.get("token") or result.get("token")}
        body = {"text": caption, "attachments": [{"type": kind, "payload": payload}]}
        for delay in self.UPLOAD_RETRIES:
            try:
                self._send(user_id, body)
                return
            except HttpError as e:
                if e.status != 400:
                    raise
                time.sleep(delay)
        self._send(user_id, body)


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
    media, other = [], False
    for att in body.get("attachments") or []:
        url = (att.get("payload") or {}).get("url")
        if att.get("type") in (IMAGE, AUDIO) and url:
            media.append(Media(att["type"], url))
        elif att.get("type") != "inline_keyboard":
            other = True
    return Inbound(
        messenger=MAX,
        user_id=user["user_id"],
        text=None if text == "/start" else text,
        has_attachments=other,
        username=user.get("username"),
        name=_max_name(user),
        started=text == "/start",
        media=media,
    )


def _max_name(user):
    return " ".join(filter(None, [user.get("first_name"), user.get("last_name")]))
