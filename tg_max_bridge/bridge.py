"""Routing, pairing requests and admin commands."""

import logging
import threading
from dataclasses import dataclass

from .messengers import LABELS, MAX, TG, Inbound

log = logging.getLogger(__name__)

ADMIN_SLOT = 1
SLOTS = (1, 2)

HELP = (
    "/status  slots and pending requests\n"
    "/approve <request> <1|2>  bind the account to a slot\n"
    "/deny <request>  ignore the account"
)


@dataclass
class Request:
    number: int
    event: Inbound


def other_messenger(messenger):
    return MAX if messenger == TG else TG


def other_slot(slot):
    return 3 - slot


class Bridge:
    def __init__(self, cfg, state, messengers):
        self.cfg = cfg
        self.state = state
        self.messengers = messengers  # name -> client
        self.lock = threading.Lock()
        self.pending = {}  # number -> Request
        self._next = 1

    # -- identity -----------------------------------------------------------

    def slots(self, messenger):
        """Effective slot -> id map; configured values win."""
        result = dict(self.state.bindings[messenger])
        for (m, slot), uid in self.cfg.fixed.items():
            if m == messenger:
                result[slot] = uid
        return result

    def slot_of(self, messenger, user_id):
        for slot, uid in self.slots(messenger).items():
            if uid == user_id:
                return slot
        return None

    # -- events -------------------------------------------------------------

    def handle(self, ev):
        with self.lock:
            try:
                self._handle(ev)
            except Exception:
                log.exception("handling %s event failed", ev.messenger)

    def _handle(self, ev):
        slot = self.slot_of(ev.messenger, ev.user_id)
        if slot is None and self._matches_username(ev):
            self.state.bind(TG, 2, ev.user_id)
            slot = 2
            self._reply(ev, "Connected as user 2.")
        if slot is None:
            self._request(ev)
            return
        if ev.started:
            self._reply(ev, "Connected as user %d." % slot)
            return
        if slot == ADMIN_SLOT and ev.text and self._command(ev):
            return
        self._relay(ev, slot)

    def _matches_username(self, ev):
        wanted = self.cfg.tg_user_2_username
        return bool(wanted and ev.messenger == TG and ev.username
                    and ev.username.lower() == wanted)

    def _request(self, ev):
        if ev.user_id in self.state.denied[ev.messenger]:
            return
        for req in self.pending.values():
            if (req.event.messenger, req.event.user_id) == (ev.messenger, ev.user_id):
                self._reply(ev, "Waiting for the admin to approve this account.")
                return
        req = Request(self._next, ev)
        self._next += 1
        self.pending[req.number] = req
        self._reply(ev, "Request sent to the admin.")
        self._notify_admin(
            "Request #%d from %s: %s\n/approve %d 1  as user 1\n"
            "/approve %d 2  as user 2\n/deny %d"
            % (req.number, LABELS[ev.messenger], describe(ev),
               req.number, req.number, req.number))

    def _command(self, ev):
        parts = ev.text.split()
        cmd = parts[0].lower()
        if cmd == "/status":
            self._reply(ev, self._status())
        elif cmd == "/help":
            self._reply(ev, HELP)
        elif cmd == "/approve":
            self._approve(ev, parts[1:])
        elif cmd == "/deny":
            self._deny(ev, parts[1:])
        else:
            return False
        return True

    def _approve(self, ev, args):
        req = self._take(ev, args)
        if req is None:
            return
        if len(args) != 2 or args[1] not in ("1", "2"):
            self._reply(ev, "Usage: /approve <request> <1|2>")
            return
        slot = int(args[1])
        target = req.event
        self.state.bind(target.messenger, slot, target.user_id)
        del self.pending[req.number]
        self._reply(ev, "Bound %s account %d as user %d."
                    % (LABELS[target.messenger], target.user_id, slot))
        self._reply(target, "Connected as user %d." % slot)

    def _deny(self, ev, args):
        req = self._take(ev, args)
        if req is None:
            return
        target = req.event
        self.state.deny(target.messenger, target.user_id)
        del self.pending[req.number]
        self._reply(ev, "Denied %s account %d." % (LABELS[target.messenger], target.user_id))

    def _take(self, ev, args):
        """Pending request named by the first argument, or None."""
        if not args or not args[0].isdigit() or int(args[0]) not in self.pending:
            self._reply(ev, "No such request.\n" + self._status())
            return None
        return self.pending[int(args[0])]

    def _status(self):
        lines = []
        for m in (TG, MAX):
            slots = self.slots(m)
            lines.append("%s: user 1 = %s, user 2 = %s" % (
                LABELS[m], slots.get(1, "unbound"), slots.get(2, "unbound")))
        for req in self.pending.values():
            lines.append("Request #%d from %s: %s"
                         % (req.number, LABELS[req.event.messenger], describe(req.event)))
        return "\n".join(lines)

    # -- relay --------------------------------------------------------------

    def _relay(self, ev, slot):
        dest = other_messenger(ev.messenger)
        dest_id = self.slots(dest).get(other_slot(slot))
        if dest_id is None:
            self._reply(ev, "User %d is not connected on %s yet."
                        % (other_slot(slot), LABELS[dest]))
            return
        if ev.text:
            try:
                self.messengers[dest].send(dest_id, ev.text)
            except Exception as e:
                log.error("send to %s %s failed: %s", dest, dest_id, e)
                self._reply(ev, "Delivery to %s failed." % LABELS[dest])
        if ev.has_attachments:
            self._reply(ev, "Only text is relayed in this version.")

    def _reply(self, ev, text):
        try:
            self.messengers[ev.messenger].send(ev.user_id, text)
        except Exception as e:
            log.error("reply to %s %s failed: %s", ev.messenger, ev.user_id, e)

    def _notify_admin(self, text):
        try:
            self.messengers[TG].send(self.cfg.tg_admin_id, text)
        except Exception as e:
            log.error("notifying the admin failed: %s", e)


def describe(ev):
    parts = [ev.name or "no name"]
    if ev.username:
        parts.append("@" + ev.username)
    parts.append("id %d" % ev.user_id)
    return " ".join(parts)
