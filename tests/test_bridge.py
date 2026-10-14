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


def test_first_request_on_empty_messenger_asks_whose_account(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(MAX, 2000, None, name="Anna", started=True))
    assert mx.sent == [(2000, "Request sent to the admin.")]
    assert tg.sent == [(100, "Request #1: Anna (id 2000) wrote to the Max bot.\n"
                             "Is this your account?")]
    assert tg.buttons == [(100, [[("Yes, it is me", "approve:1:1"),
                                  ("No, the other person", "approve:1:2")],
                                 [("Ignore", "deny:1")]])]
    bridge.handle(Inbound(MAX, 2000, "again"))
    assert mx.sent[-1] == (2000, "Waiting for the admin to approve this account.")
    assert len(tg.sent) == 1


def test_request_for_last_seat_offers_connect_only(world):
    bridge, tg, mx, state = world
    state.bind(MAX, 1, 1000)
    bridge.handle(Inbound(MAX, 2000, "hi", name="Anna"))
    assert tg.sent == [(100, "Request #1: Anna (id 2000) wrote to the Max bot.\n"
                             "Connect as user 2, the other person?")]
    assert tg.buttons == [(100, [[("Connect", "approve:1:2"), ("Ignore", "deny:1")]])]
    bridge.handle(Inbound(TG, 100, "/approve 1"))
    assert state.bindings[MAX] == {1: 1000, 2: 2000}
    assert tg.sent[-1] == (100, "Anna (id 2000) on Max is now user 2, the other person.")
    assert mx.sent[-1] == (2000, "You are connected as user 2, the other person.")


def test_button_press_applies_and_edits(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(MAX, 2000, None, name="Anna", started=True))
    bridge.handle(Inbound(TG, 100, None, callback="approve:1:2", callback_id="c1", message_id=9))
    assert state.bindings[MAX] == {2: 2000}
    assert tg.answered == [("c1", "Done", "Anna (id 2000) on Max is now user 2, the other person.")]
    assert mx.sent[-1] == (2000, "You are connected as user 2, the other person.")
    bridge.handle(Inbound(TG, 100, None, callback="approve:1:2", callback_id="c2", message_id=9))
    assert tg.answered[-1] == ("c2", "This request is already handled.", "Already handled.")


def test_button_press_from_non_admin_is_ignored(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(MAX, 2000, None, name="Anna", started=True))
    bridge.handle(Inbound(TG, 555, None, callback="approve:1:2", callback_id="c1", message_id=9))
    assert state.bindings[MAX] == {} and tg.answered == []


def test_approve_by_text_with_explicit_slot(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(MAX, 2000, None, name="Anna", started=True))
    bridge.handle(Inbound(TG, 100, "/approve 1"))
    assert tg.sent[-1] == (100, "Usage: /approve <request> [1|2]")
    bridge.handle(Inbound(TG, 100, "/approve 1 2"))
    assert state.bindings[MAX] == {2: 2000} and bridge.pending == {}
    bridge.handle(Inbound(TG, 100, "text"))
    assert mx.sent[-1] == (2000, "text")


def test_admin_can_approve_from_max_once_bound(world):
    bridge, tg, mx, state = world
    state.bind(MAX, 1, 1000)
    bridge.handle(Inbound(TG, 200, None, name="B", started=True))
    bridge.handle(Inbound(MAX, 1000, "/approve 1"))
    assert state.bindings[TG] == {2: 200}
    assert tg.sent[-1] == (200, "You are connected as user 2, the other person.")


def test_deny_silences_the_account(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(MAX, 3000, "spam", name="X"))
    bridge.handle(Inbound(TG, 100, None, callback="deny:1", callback_id="c1", message_id=1))
    assert 3000 in state.denied[MAX]
    assert tg.answered[-1][2] == "X (id 3000) on Max is ignored from now on."
    sent_before = len(mx.sent), len(tg.sent)
    bridge.handle(Inbound(MAX, 3000, "spam again"))
    assert (len(mx.sent), len(tg.sent)) == sent_before


def test_bad_request_number_shows_status(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(TG, 100, "/deny 9"))
    assert tg.sent[-1][1].startswith("No such request.\nTelegram, user 1, the admin: id 100")


def test_status_lists_slots_and_requests(world):
    bridge, tg, mx, state = world
    state.bind(MAX, 2, 2000)
    bridge.handle(Inbound(MAX, 1000, "hi", name="Me", username="me"))
    bridge.handle(Inbound(TG, 100, "/status"))
    assert tg.sent[-1][1] == (
        "Telegram, user 1, the admin: id 100\n"
        "Telegram, user 2, the other person: not connected\n"
        "Max, user 1, the admin: not connected\n"
        "Max, user 2, the other person: id 2000\n"
        "Request #1: Me @me (id 1000) wrote to the Max bot.")


def test_non_admin_slash_text_is_relayed(world):
    bridge, tg, mx, state = world
    bind_all(state)
    bridge.handle(Inbound(TG, 200, "/status"))
    assert mx.sent == [(1000, "/status")]


def test_start_from_bound_user_confirms_slot(world):
    bridge, tg, mx, state = world
    bridge.handle(Inbound(TG, 100, None, started=True))
    assert tg.sent == [(100, "You are connected as user 1, the admin.")]


def test_configured_username_binds_user_2(world):
    bridge, tg, mx, state = world
    bridge.cfg.tg_usernames[2] = "anna"
    bridge.handle(Inbound(TG, 200, "hi", username="Anna"))
    assert state.bindings[TG] == {2: 200}
    assert tg.sent[0] == (200, "You are connected as user 2, the other person.")


def test_configured_ids_override_state(world):
    bridge, tg, mx, state = world
    state.bind(MAX, 2, 2000)
    bridge.cfg.fixed[(MAX, 2)] = 2500
    assert bridge.slots(MAX) == {2: 2500}
    assert bridge.slot_of(MAX, 2000) is None


def test_configured_admin_username_binds_and_receives_waiting_requests(world):
    bridge, tg, mx, state = world
    del bridge.cfg.fixed[(TG, 1)]
    bridge.cfg.tg_usernames[1] = "owner"
    bridge.handle(Inbound(MAX, 2000, None, name="Anna", started=True))
    assert tg.sent == []  # no owner bound yet: logged only
    bridge.handle(Inbound(TG, 300, "/status", username="Owner"))
    assert state.bindings[TG] == {1: 300}
    assert tg.sent[0] == (300, "You are connected as user 1, the admin.")
    assert tg.sent[1][1].startswith("Request #1: Anna (id 2000) wrote to the Max bot.")
    assert tg.buttons[0][0] == 300


def test_unbind_clears_runtime_slot_only(world):
    bridge, tg, mx, state = world
    state.bind(MAX, 2, 2000)
    bridge.handle(Inbound(TG, 100, "/unbind max 2"))
    assert state.bindings[MAX] == {}
    assert tg.sent[-1] == (100, "User 2 on Max is disconnected.")
    bridge.handle(Inbound(TG, 100, "/unbind tg 1"))
    assert tg.sent[-1] == (100, "User 1 on Telegram is set in the configuration and cannot be unbound.")
    bridge.handle(Inbound(TG, 100, "/unbind max 2"))
    assert tg.sent[-1] == (100, "User 2 on Max is not connected.")
    bridge.handle(Inbound(TG, 100, "/unbind x 2"))
    assert tg.sent[-1] == (100, "Usage: /unbind <tg|max> <1|2>")


def test_bots_lists_both_accounts(world):
    bridge, tg, mx, state = world
    bridge.bots = {TG: "bot_a", MAX: "bot_b"}
    bridge.handle(Inbound(TG, 100, "/bots"))
    assert tg.sent[-1] == (100, "Telegram: bot_a\nMax: bot_b")


def test_pinned_username_does_not_rebind(world):
    bridge, tg, mx, state = world
    bridge.cfg.tg_usernames[2] = "anna"
    bridge.handle(Inbound(TG, 200, "hi", username="anna"))
    bridge.handle(Inbound(TG, 201, "hi", username="anna"))
    assert state.bindings[TG] == {2: 200}
    assert tg.sent == [(200, "You are connected as user 2, the other person.")]


def test_unknown_account_ignored_when_slots_full(world):
    bridge, tg, mx, state = world
    bind_all(state)
    bridge.handle(Inbound(MAX, 3000, "hi", name="X"))
    bridge.handle(Inbound(TG, 300, None, started=True))
    assert mx.sent == [] and tg.sent == [] and bridge.pending == {}
