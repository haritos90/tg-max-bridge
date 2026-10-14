"""Routing, pairing requests and admin commands."""

import logging
import re
import threading
from dataclasses import dataclass

from .messengers import LABELS, MAX, TG, Inbound

log = logging.getLogger(__name__)

ADMIN_SLOT = 1
SLOTS = (1, 2)
WHO = {1: "user 1, the admin", 2: "user 2, the other person"}
LINK_MARK = "[link removed]"
# URL with a scheme, mailto/tel, or a bare host.tld with a path;
# trailing punctuation stays in the text.
_END = r"(?=[\s,;)\]]|[.?!:](?:\s|$)|$)"
LINK_RE = re.compile(
    r"(?i)\b(?:(?:[a-z][a-z0-9+.-]*://|www\.|mailto:|tel:)\S+?" + _END
    + r"|(?:[^\s@]+@)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*?)?" + _END + ")")


def strip_links(text):
    """Text with every link replaced; the number of links removed."""
    return LINK_RE.subn(LINK_MARK, text)

USER_COMMANDS = [("start", "Connect to the bridge")]
ADMIN_COMMANDS = USER_COMMANDS + [
    ("status", "Who is connected and who is waiting"),
    ("approve", "Connect a waiting account"),
    ("deny", "Ignore a waiting account"),
    ("unbind", "Forget a connected account"),
    ("bots", "The two bot accounts"),
    ("help", "The command list"),
]

HELP = (
    "/status  who is connected and who is waiting\n"
    "/approve <request>  connect the account to the free seat\n"
    "/approve <request> <1|2>  connect it as you (1) or the other person (2)\n"
    "/deny <request>  ignore the account\n"
    "/unbind <tg|max> <1|2>  forget a connected account\n"
    "/bots  the two bot accounts"
)


@dataclass
class Request:
    number: int
    event: Inbound


def request_from_state(number, rec):
    """Rebuild a request from its state-file record."""
    return Request(number, Inbound(rec["messenger"], rec["user_id"], None,
                                   username=rec.get("username"), name=rec.get("name") or ""))


def other_messenger(messenger):
    return MAX if messenger == TG else TG


def other_slot(slot):
    return 3 - slot


class Bridge:
    def __init__(self, cfg, state, messengers):
        self.cfg = cfg
        self.state = state
        self.messengers = messengers  # name -> client
        self.bots = {}  # name -> bot username, filled at start
        self.lock = threading.Lock()

    @property
    def pending(self):
        """number -> Request, rebuilt from the state file."""
        return {n: request_from_state(n, rec) for n, rec in self.state.pending.items()}

    def publish_menus(self):
        """Start for everyone; the admin commands in the admin's Telegram chat."""
        for m in self.messengers.values():
            try:
                m.set_commands(USER_COMMANDS)
            except Exception as e:
                log.error("%s menu failed: %s", m.name, e)
        self._publish_admin_menu()

    def _publish_admin_menu(self):
        admin = self.slots(TG).get(ADMIN_SLOT)
        if admin is None:
            return
        try:
            self.messengers[TG].set_commands(ADMIN_COMMANDS, admin)
        except Exception as e:
            log.error("admin menu failed: %s", e)

    def resend_pending(self):
        """Waiting requests to the admin: after a restart or on /status."""
        with self.lock:
            for req in self.pending.values():
                self._notify_admin(req)

    # -- identity -----------------------------------------------------------

    def slots(self, messenger):
        """Effective slot -> id map; configured values win."""
        result = dict(self.state.bindings[messenger])
        for (m, slot), uid in self.cfg.fixed.items():
            if m == messenger:
                result[slot] = uid
        return result

    def free_slots(self, messenger):
        taken = self.slots(messenger)
        return [slot for slot in SLOTS if slot not in taken]

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
        if ev.callback is not None:
            # Buttons exist only on admin messages.
            if slot == ADMIN_SLOT:
                self._callback(ev)
            return
        if slot is None:
            slot = self._bind_by_username(ev)
            if slot is not None:
                return
        if slot is None:
            self._request(ev)
            return
        if ev.started:
            self._reply(ev, "You are connected as %s." % WHO[slot])
            return
        if slot == ADMIN_SLOT and ev.text and self._command(ev):
            return
        self._relay(ev, slot)

    def _bind_by_username(self, ev):
        """Bind a configured Telegram username; the slot, or None."""
        if ev.messenger != TG or not ev.username:
            return None
        for slot, name in self.cfg.tg_usernames.items():
            # Pinned once: the stored id is authoritative.
            if slot in self.state.bindings[TG]:
                continue
            if ev.username.lower() == name:
                self.state.bind(TG, slot, ev.user_id)
                self._reply(ev, "You are connected as %s." % WHO[slot])
                if slot == ADMIN_SLOT:
                    self._publish_admin_menu()
                    # Requests that waited for the admin.
                    for req in list(self.pending.values()):
                        self._notify_admin(req)
                return slot
        return None

    def _request(self, ev):
        if ev.user_id in self.state.denied[ev.messenger]:
            return
        if len(self.slots(ev.messenger)) == len(SLOTS):
            log.info("ignoring %s account %s: slots full", ev.messenger, ev.user_id)
            return
        for req in self.pending.values():
            if (req.event.messenger, req.event.user_id) == (ev.messenger, ev.user_id):
                self._reply(ev, "Waiting for the admin to approve this account.")
                return
        number = self.state.add_request(ev.messenger, ev.user_id, ev.name, ev.username)
        self._reply(ev, "Request sent to the admin.")
        self._notify_admin(Request(number, ev))

    def _notify_admin(self, req):
        admin = self.slots(TG).get(ADMIN_SLOT)
        if admin is None:
            log.warning("no admin bound on Telegram; request #%d waits", req.number)
            return
        n = req.number
        text = "Request #%d: %s wrote to the %s bot." % (
            n, describe(req.event), LABELS[req.event.messenger])
        free = self.free_slots(req.event.messenger)
        if len(free) == 1:
            # Only one seat left: no question.
            text += "\nConnect as %s?" % WHO[free[0]]
            buttons = [[("Connect", "approve:%d:%d" % (n, free[0])),
                        ("Ignore", "deny:%d" % n)]]
        else:
            text += "\nIs this your account?"
            buttons = [[("Yes, it is me", "approve:%d:1" % n),
                        ("No, the other person", "approve:%d:2" % n)],
                       [("Ignore", "deny:%d" % n)]]
        try:
            self.messengers[TG].send(admin, text, buttons)
        except Exception as e:
            log.error("notifying the admin failed: %s", e)

    # -- admin commands -----------------------------------------------------

    def _callback(self, ev):
        parts = ev.callback.split(":")
        req = self.pending.get(int(parts[1])) if len(parts) > 1 and parts[1].isdigit() else None
        if req is None:
            self._answer(ev, "This request is already handled.", "Already handled.")
        elif parts[0] == "approve" and len(parts) == 3 and parts[2] in ("1", "2"):
            outcome = self._approve(req, int(parts[2]))
            self._answer(ev, "Done", outcome)
        elif parts[0] == "deny":
            self._answer(ev, "Done", self._deny(req))

    def _command(self, ev):
        parts = ev.text.split()
        cmd = parts[0].lower()
        if cmd == "/status":
            self._reply(ev, self._status())
            if ev.messenger == TG:
                for req in self.pending.values():
                    self._notify_admin(req)
        elif cmd == "/help":
            self._reply(ev, HELP)
        elif cmd == "/approve":
            req = self._take(ev, parts[1:])
            if req is None:
                return True
            free = self.free_slots(req.event.messenger)
            if len(parts) == 2 and len(free) == 1:
                slot = free[0]  # the one seat left
            elif len(parts) == 3 and parts[2] in ("1", "2"):
                slot = int(parts[2])
            else:
                self._reply(ev, "Usage: /approve <request> [1|2]")
                return True
            self._reply(ev, self._approve(req, slot))
        elif cmd == "/deny":
            req = self._take(ev, parts[1:])
            if req is not None:
                self._reply(ev, self._deny(req))
        elif cmd == "/unbind":
            self._unbind(ev, parts[1:])
        elif cmd == "/bots":
            self._reply(ev, "\n".join("%s: %s" % (LABELS[m], self.bots.get(m, "unknown"))
                                      for m in (TG, MAX)))
        else:
            return False
        return True

    def _approve(self, req, slot):
        """Bind the request's account; the outcome sentence."""
        target = req.event
        self.state.bind(target.messenger, slot, target.user_id)
        self.state.drop_request(req.number)
        if (target.messenger, slot) == (TG, ADMIN_SLOT):
            self._publish_admin_menu()
        self._reply(target, "You are connected as %s." % WHO[slot])
        return "%s on %s is now %s." % (describe(target), LABELS[target.messenger], WHO[slot])

    def _deny(self, req):
        target = req.event
        self.state.deny(target.messenger, target.user_id)
        self.state.drop_request(req.number)
        return "%s on %s is ignored from now on." % (describe(target), LABELS[target.messenger])

    def _unbind(self, ev, args):
        if len(args) != 2 or args[0] not in LABELS or args[1] not in ("1", "2"):
            self._reply(ev, "Usage: /unbind <tg|max> <1|2>")
            return
        messenger, slot = args[0], int(args[1])
        if (messenger, slot) in self.cfg.fixed:
            self._reply(ev, "User %d on %s is set in the configuration and cannot be unbound."
                        % (slot, LABELS[messenger]))
            return
        if slot not in self.state.bindings[messenger]:
            self._reply(ev, "User %d on %s is not connected." % (slot, LABELS[messenger]))
            return
        self.state.unbind(messenger, slot)
        self._reply(ev, "User %d on %s is disconnected." % (slot, LABELS[messenger]))

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
            for slot in SLOTS:
                uid = slots.get(slot)
                lines.append("%s, %s: %s" % (
                    LABELS[m], WHO[slot], "id %d" % uid if uid else "not connected"))
        if not self.pending:
            lines.append("No one is waiting.")
        for req in self.pending.values():
            lines.append("Request #%d: %s wrote to the %s bot."
                         % (req.number, describe(req.event), LABELS[req.event.messenger]))
        return "\n".join(lines)

    # -- relay --------------------------------------------------------------

    def _relay(self, ev, slot):
        dest = other_messenger(ev.messenger)
        dest_id = self.slots(dest).get(other_slot(slot))
        if dest_id is None:
            self._reply(ev, "Not delivered: %s has no %s account connected yet. "
                        "They need to open the %s bot and press Start."
                        % (WHO[other_slot(slot)], LABELS[dest], LABELS[dest]))
            return
        if ev.text:
            text, removed = strip_links(ev.text)
            try:
                self.messengers[dest].send(dest_id, text)
            except Exception as e:
                log.error("send to %s %s failed: %s", dest, dest_id, e)
                self._reply(ev, "Delivery to %s failed." % LABELS[dest])
            else:
                if removed:
                    self._reply(ev, "Links are not relayed; %d removed." % removed)
        if ev.has_attachments:
            self._reply(ev, "Only text is relayed in this version.")

    def _reply(self, ev, text):
        try:
            self.messengers[ev.messenger].send(ev.user_id, text)
        except Exception as e:
            log.error("reply to %s %s failed: %s", ev.messenger, ev.user_id, e)

    def _answer(self, ev, text, outcome):
        try:
            self.messengers[ev.messenger].answer(ev, text, outcome)
        except Exception as e:
            log.error("answering %s callback failed: %s", ev.messenger, e)


def describe(ev):
    parts = [ev.name or "no name"]
    if ev.username:
        parts.append("@" + ev.username)
    parts.append("(id %d)" % ev.user_id)
    return " ".join(parts)
