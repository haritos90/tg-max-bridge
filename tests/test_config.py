import pytest

from tg_max_bridge import config
from tg_max_bridge.messengers import MAX, TG

BASE = {"TG_BOT_TOKEN": "t", "MAX_BOT_TOKEN": "m", "TG_ADMIN_ID": "100", "HOME": "/h"}


def test_required_keys():
    with pytest.raises(config.ConfigError, match="MAX_BOT_TOKEN, TG_ADMIN_ID"):
        config.load({"TG_BOT_TOKEN": "t"})


def test_defaults():
    cfg = config.load(dict(BASE))
    assert cfg.fixed == {(TG, 1): 100}
    assert cfg.max_api_url == "https://platform-api2.max.ru"
    assert cfg.state_file == "/h/.local/state/tg-max-bridge/state.json"
    assert cfg.tg_user_2_username is None


def test_user_2_as_username_or_id():
    assert config.load({**BASE, "TG_USER_2": "@Anna"}).tg_user_2_username == "anna"
    assert config.load({**BASE, "TG_USER_2": "200"}).fixed[(TG, 2)] == 200


def test_max_ids_and_paths():
    cfg = config.load({**BASE, "MAX_USER_1": "1000", "MAX_USER_2": "2000",
                       "MAX_CA_FILE": "/ca.pem", "XDG_STATE_HOME": "/x"})
    assert cfg.fixed[(MAX, 1)] == 1000 and cfg.fixed[(MAX, 2)] == 2000
    assert cfg.max_ca_file == "/ca.pem"
    assert cfg.state_file == "/x/tg-max-bridge/state.json"


def test_bad_number():
    with pytest.raises(config.ConfigError, match="TG_ADMIN_ID"):
        config.load({**BASE, "TG_ADMIN_ID": "abc"})
