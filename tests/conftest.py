import pytest

from tg_max_bridge.bridge import Bridge
from tg_max_bridge.config import Config
from tg_max_bridge.messengers import MAX, TG
from tg_max_bridge.state import State


class FakeMessenger:
    def __init__(self, name):
        self.name = name
        self.sent = []  # (user_id, text)
        self.fail = False

    def send(self, user_id, text):
        if self.fail:
            raise RuntimeError("down")
        self.sent.append((user_id, text))


@pytest.fixture
def world(tmp_path):
    cfg = Config(tg_token="t", max_token="m",
                 state_file=str(tmp_path / "state.json"))
    cfg.fixed[(TG, 1)] = 100
    state = State(cfg.state_file)
    tg, mx = FakeMessenger(TG), FakeMessenger(MAX)
    return Bridge(cfg, state, {TG: tg, MAX: mx}), tg, mx, state
