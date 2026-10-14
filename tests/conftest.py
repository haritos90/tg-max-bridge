import pytest

from tg_max_bridge.bridge import Bridge
from tg_max_bridge.config import Config
from tg_max_bridge.messengers import MAX, TG
from tg_max_bridge.state import State


class FakeMessenger:
    def __init__(self, name):
        self.name = name
        self.sent = []  # (user_id, text)
        self.buttons = []  # (user_id, rows) per send carrying buttons
        self.answered = []  # (callback_id, text, outcome)
        self.menus = []  # (user_id or None, names)
        self.fail = False

    def set_commands(self, commands, user_id=None):
        self.menus.append((user_id, [n for n, _ in commands]))

    def download(self, media):
        if self.fail:
            raise RuntimeError("down")
        return b"bytes-of-" + media.ref.encode(), media.ref + ".bin", "application/x-test"

    def send_media(self, user_id, kind, data, filename, mime, caption=None):
        if self.fail:
            raise RuntimeError("down")
        self.sent.append((user_id, (kind, data, filename, mime, caption)))

    def send(self, user_id, text, buttons=None):
        if self.fail:
            raise RuntimeError("down")
        self.sent.append((user_id, text))
        if buttons:
            self.buttons.append((user_id, buttons))
        return len(self.sent)

    def answer(self, ev, text, outcome=None):
        self.answered.append((ev.callback_id, text, outcome))


@pytest.fixture
def world(tmp_path):
    cfg = Config(tg_token="t", max_token="m",
                 state_file=str(tmp_path / "state.json"))
    cfg.fixed[(TG, 1)] = 100
    state = State(cfg.state_file)
    tg, mx = FakeMessenger(TG), FakeMessenger(MAX)
    return Bridge(cfg, state, {TG: tg, MAX: mx}), tg, mx, state
