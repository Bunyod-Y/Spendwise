"""Registry of bot users and their report bookkeeping (data/users.json).

Only the Telegram user ID and report state are stored: no names, usernames
or phone numbers. Groups use the same class (data/groups.json), keyed by chat ID.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path


class UserRegistry:
    def __init__(self, path: Path):
        self.path = path
        self._users: dict[str, dict] = {}
        if path.exists():
            self._users = json.loads(path.read_text(encoding="utf-8"))

    def ids(self) -> list[int]:
        return [int(uid) for uid in self._users]

    def get(self, uid: int) -> dict | None:
        return self._users.get(str(uid))

    def register(self, uid: int, last_week: str, last_month: str) -> bool:
        """Add a new user. Returns True if the user was not known before.

        `last_week` / `last_month` mark reports as already sent up to now, so a
        new user never gets a report for a period before they joined.
        """
        if str(uid) in self._users:
            return False
        self._users[str(uid)] = {
            "joined": date.today().isoformat(),
            "reports": True,
            "last_week": last_week,
            "last_month": last_month,
        }
        self._save()
        return True

    def update(self, uid: int, **fields) -> None:
        self._users[str(uid)].update(fields)
        self._save()

    def remove(self, uid: int) -> None:
        if self._users.pop(str(uid), None) is not None:
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._users, indent=2), encoding="utf-8")
        tmp.replace(self.path)
