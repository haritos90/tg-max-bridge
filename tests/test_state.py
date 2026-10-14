from tg_max_bridge.messengers import MAX, TG
from tg_max_bridge.state import State


def test_roundtrip(tmp_path):
    path = tmp_path / "s" / "state.json"
    s = State(str(path))
    s.bind(TG, 2, 200)
    s.bind(MAX, 1, 1000)
    s.deny(MAX, 3000)
    loaded = State(str(path)).load()
    assert loaded.bindings == {TG: {2: 200}, MAX: {1: 1000}}
    assert loaded.denied == {TG: set(), MAX: {3000}}


def test_rebinding_moves_the_account(tmp_path):
    s = State(str(tmp_path / "state.json"))
    s.bind(MAX, 1, 1000)
    s.bind(MAX, 2, 1000)
    assert s.bindings[MAX] == {2: 1000}


def test_bind_clears_denial(tmp_path):
    s = State(str(tmp_path / "state.json"))
    s.deny(TG, 5)
    s.bind(TG, 2, 5)
    assert s.denied[TG] == set()


def test_missing_file_loads_empty(tmp_path):
    s = State(str(tmp_path / "none.json")).load()
    assert s.bindings == {TG: {}, MAX: {}}


def test_pending_requests_survive_reload(tmp_path):
    s = State(str(tmp_path / "state.json"))
    assert s.add_request(MAX, 2000, "Anna", None) == 1
    s.drop_request(1)
    assert s.add_request(TG, 300, "B", "b") == 2
    loaded = State(s.path).load()
    assert loaded.pending == {2: {"messenger": TG, "user_id": 300, "name": "B", "username": "b"}}
    assert loaded.next_request == 3
