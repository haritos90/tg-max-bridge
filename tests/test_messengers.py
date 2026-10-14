from tg_max_bridge.messengers import MAX, TG, parse_max, parse_telegram


def tg_update(text=None, chat_type="private", **extra):
    msg = {"message_id": 1, "chat": {"id": 100, "type": chat_type},
           "from": {"id": 100, "is_bot": False, "first_name": "A", "last_name": "B",
                    "username": "ab"}}
    if text is not None:
        msg["text"] = text
    msg.update(extra)
    return {"update_id": 7, "message": msg}


def test_telegram_text():
    ev = parse_telegram(tg_update("hi"))
    assert (ev.messenger, ev.user_id, ev.text, ev.username, ev.name) == (TG, 100, "hi", "ab", "A B")
    assert not ev.has_attachments and not ev.started


def test_telegram_start_and_media():
    assert parse_telegram(tg_update("/start")).started
    ev = parse_telegram(tg_update(photo=[{"file_id": "x"}]))
    assert ev.text is None and ev.has_attachments


def test_telegram_ignores_groups_and_non_messages():
    assert parse_telegram(tg_update("hi", chat_type="group")) is None
    assert parse_telegram({"update_id": 1, "edited_message": {}}) is None


def test_max_message():
    upd = {"update_type": "message_created", "timestamp": 1,
           "message": {"sender": {"user_id": 1000, "first_name": "Me", "is_bot": False},
                       "recipient": {"chat_id": 5, "chat_type": "dialog"},
                       "body": {"mid": "m", "seq": 1, "text": "hi", "attachments": None}}}
    ev = parse_max(upd)
    assert (ev.messenger, ev.user_id, ev.text, ev.name) == (MAX, 1000, "hi", "Me")
    upd["message"]["body"] = {"mid": "m", "seq": 2, "attachments": [{"type": "image"}]}
    ev = parse_max(upd)
    assert ev.text is None and ev.has_attachments


def test_max_started_and_other_updates():
    ev = parse_max({"update_type": "bot_started", "timestamp": 1, "chat_id": 5,
                    "user": {"user_id": 1000, "first_name": "Me", "is_bot": False}})
    assert ev.started and ev.user_id == 1000
    assert parse_max({"update_type": "message_removed", "timestamp": 1}) is None
    chat = {"update_type": "message_created", "timestamp": 1,
            "message": {"sender": {"user_id": 1, "first_name": "x", "is_bot": False},
                        "recipient": {"chat_id": 5, "chat_type": "chat"}, "body": {}}}
    assert parse_max(chat) is None


def test_telegram_callback():
    ev = parse_telegram({"update_id": 2, "callback_query": {
        "id": "c9", "data": "approve:1:2", "from": {"id": 100, "is_bot": False, "first_name": "A"},
        "message": {"message_id": 44}}})
    assert (ev.messenger, ev.user_id, ev.callback, ev.callback_id, ev.message_id) == (
        TG, 100, "approve:1:2", "c9", 44)
    assert ev.text is None and not ev.started


def test_max_typed_start_counts_as_started():
    upd = {"update_type": "message_created", "timestamp": 1,
           "message": {"sender": {"user_id": 1000, "first_name": "Me", "is_bot": False},
                       "recipient": {"chat_id": 5, "chat_type": "dialog"},
                       "body": {"mid": "m", "seq": 1, "text": "/start"}}}
    ev = parse_max(upd)
    assert ev.started and ev.text is None
