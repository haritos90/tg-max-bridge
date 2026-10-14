"""Bindings and denials, persisted as one JSON file."""

import json
import os
import tempfile

from .messengers import MAX, TG


class State:
    def __init__(self, path):
        self.path = path
        self.bindings = {TG: {}, MAX: {}}  # messenger -> {slot: id}
        self.denied = {TG: set(), MAX: set()}
        self.pending = {}  # number -> {messenger, user_id, name, username}
        self.next_request = 1

    def load(self):
        if not os.path.exists(self.path):
            return self
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        for m in (TG, MAX):
            raw = data.get("bindings", {}).get(m, {})
            self.bindings[m] = {int(k): int(v) for k, v in raw.items()}
            self.denied[m] = set(data.get("denied", {}).get(m, []))
        self.pending = {int(k): v for k, v in data.get("pending", {}).items()}
        self.next_request = int(data.get("next_request", 1))
        return self

    def save(self):
        data = {
            "bindings": {m: {str(k): v for k, v in b.items()}
                         for m, b in self.bindings.items()},
            "denied": {m: sorted(d) for m, d in self.denied.items()},
            "pending": {str(k): v for k, v in self.pending.items()},
            "next_request": self.next_request,
        }
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        # Write whole, then replace: never a torn file.
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path) or ".")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, self.path)

    def bind(self, messenger, slot, user_id):
        # One account holds at most one slot.
        for s, uid in list(self.bindings[messenger].items()):
            if uid == user_id:
                del self.bindings[messenger][s]
        self.bindings[messenger][slot] = user_id
        self.denied[messenger].discard(user_id)
        self.save()

    def unbind(self, messenger, slot):
        self.bindings[messenger].pop(slot, None)
        self.save()

    def add_request(self, messenger, user_id, name, username):
        number = self.next_request
        self.next_request += 1
        self.pending[number] = {"messenger": messenger, "user_id": user_id,
                                "name": name, "username": username}
        self.save()
        return number

    def drop_request(self, number):
        self.pending.pop(number, None)
        self.save()

    def deny(self, messenger, user_id):
        self.denied[messenger].add(user_id)
        self.save()
