from tg_max_bridge.messengers import MAX, TG, Inbound


def bind_all(state):
    state.bind(TG, 2, 200)
    state.bind(MAX, 1, 1000)
    state.bind(MAX, 2, 2000)


def test_text_is_relayed_in_all_four_directions(world):
    bridge, tg, mx, state = world
    bind_all(state)
    bridge.handle(Inbound(TG, 100, "a"))
    bridge.handle(Inbound(MAX, 1000, "b"))
    bridge.handle(Inbound(TG, 200, "c"))
    bridge.handle(Inbound(MAX, 2000, "d"))
    assert mx.sent == [(2000, "a"), (1000, "c")]
    assert tg.sent == [(200, "b"), (100, "d")]


def test_unbound_destination_is_reported_to_sender(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(TG, 100, "hello"))
    assert mx.sent == []
    assert tg.sent == [(100, "User 2 is not connected on Max yet.")]


def test_attachments_are_not_relayed(world):
    bridge, tg, mx, state = world
    bind_all(state)
    bridge.handle(Inbound(TG, 100, "caption", has_attachments=True))
    bridge.handle(Inbound(TG, 100, None, has_attachments=True))
    assert mx.sent == [(2000, "caption")]
    assert tg.sent == [(100, "Only text is relayed in this version.")] * 2


def test_send_failure_is_reported_to_sender(world):
    bridge, tg, mx, state = world
    bind_all(state)
    mx.fail = True
    bridge.handle(Inbound(TG, 100, "x"))
    assert tg.sent == [(100, "Delivery to Max failed.")]


def test_unknown_account_creates_request_and_notifies_admin(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(MAX, 2000, None, name="Anna", started=True))
    assert mx.sent == [(2000, "Request sent to the admin.")]
    assert tg.sent[0][0] == 100
    assert tg.sent[0][1].startswith("Request #1 from Max: Anna id 2000\n/approve 1 1")
    bridge.handle(Inbound(MAX, 2000, "again"))
    assert mx.sent[-1] == (2000, "Waiting for the admin to approve this account.")
    assert len(tg.sent) == 1


def test_approve_binds_and_confirms_both_sides(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(MAX, 2000, None, name="Anna", started=True))
    bridge.handle(Inbound(TG, 100, "/approve 1 2"))
    assert state.bindings[MAX] == {2: 2000}
    assert bridge.pending == {}
    assert tg.sent[-1] == (100, "Bound Max account 2000 as user 2.")
    assert mx.sent[-1] == (2000, "Connected as user 2.")
    bridge.handle(Inbound(TG, 100, "text"))
    assert mx.sent[-1] == (2000, "text")


def test_admin_can_approve_from_max_once_bound(world):
    bridge, tg, mx, state = world
    state.bind(MAX, 1, 1000)
    bridge.handle(Inbound(TG, 200, None, name="B", started=True))
    bridge.handle(Inbound(MAX, 1000, "/approve 1 2"))
    assert state.bindings[TG] == {2: 200}
    assert tg.sent[-1] == (200, "Connected as user 2.")


def test_deny_silences_the_account(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(MAX, 3000, "spam", name="X"))
    bridge.handle(Inbound(TG, 100, "/deny 1"))
    assert 3000 in state.denied[MAX]
    sent_before = len(mx.sent), len(tg.sent)
    bridge.handle(Inbound(MAX, 3000, "spam again"))
    assert (len(mx.sent), len(tg.sent)) == sent_before


def test_bad_request_number_shows_status(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(TG, 100, "/approve 9 2"))
    assert tg.sent[-1][1].startswith("No such request.\nTelegram: user 1 = 100, user 2 = unbound")


def test_status_lists_slots_and_requests(world):
    bridge, tg, mx, state = world
    state.bind(MAX, 2, 2000)
    bridge.handle(Inbound(MAX, 1000, "hi", name="Me", username="me"))
    bridge.handle(Inbound(TG, 100, "/status"))
    assert tg.sent[-1][1] == (
        "Telegram: user 1 = 100, user 2 = unbound\n"
        "Max: user 1 = unbound, user 2 = 2000\n"
        "Request #1 from Max: Me @me id 1000")


def test_non_admin_slash_text_is_relayed(world):
    bridge, tg, mx, state = world
    bind_all(state)
    bridge.handle(Inbound(TG, 200, "/status"))
    assert mx.sent == [(1000, "/status")]


def test_start_from_bound_user_confirms_slot(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(TG, 100, None, started=True))
    assert tg.sent == [(100, "Connected as user 1.")]


def test_configured_username_binds_user_2(world):
    bridge, tg, mx, state = world
    bridge.cfg.tg_user_2_username = "anna"
    bridge.handle(Inbound(TG, 200, "hi", username="Anna"))
    assert state.bindings[TG] == {2: 200}
    assert tg.sent[0] == (200, "Connected as user 2.")


def test_configured_ids_override_state(world):
    bridge, tg, mx, state = world
    state.bind(MAX, 2, 2000)
    bridge.cfg.fixed[(MAX, 2)] = 2500
    assert bridge.slots(MAX) == {2: 2500}
    assert bridge.slot_of(MAX, 2000) is None
