"""Per-user encryption key management (envelope encryption).

Each user has a random data key that encrypts their files. The data key is
stored only in *wrapped* form (encrypted with a key derived from the user's
password using scrypt) in `<user_dir>/vault.json`. The password and the
unwrapped data key are never written to disk: the data key lives in the bot's
memory while the user is unlocked. Without the password, the files (and the
wrapped key) cannot be opened, not even by whoever runs the server.

Changing the password only re-wraps the data key, so files are not rewritten.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

META_NAME = "vault.json"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**15, 8, 1  # ~32 MB and ~100 ms per attempt
MIN_PASSWORD, MAX_PASSWORD = 6, 128


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> Fernet:
    key = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=128 * 1024 * 1024, dklen=32
    )
    return Fernet(base64.urlsafe_b64encode(key))


class Vault:
    def __init__(self, user_dir: Path):
        self.dir = user_dir
        self.path = user_dir / META_NAME

    def exists(self) -> bool:
        return self.path.exists()

    def _write(self, data_key: bytes, password: str) -> None:
        salt = os.urandom(16)
        kek = _derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
        meta = {
            "v": 1,
            "salt": base64.b64encode(salt).decode(),
            "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
            "wrapped_key": kek.encrypt(data_key).decode(),
        }
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(meta), encoding="utf-8")
        tmp.replace(self.path)

    def create(self, password: str) -> Fernet:
        """Set up a new vault. Returns the cipher for the new data key."""
        data_key = Fernet.generate_key()
        self._write(data_key, password)
        return Fernet(data_key)

    def _unwrap(self, password: str) -> bytes | None:
        meta = json.loads(self.path.read_text(encoding="utf-8"))
        kek = _derive(password, base64.b64decode(meta["salt"]), meta["n"], meta["r"], meta["p"])
        try:
            return kek.decrypt(meta["wrapped_key"].encode())
        except InvalidToken:
            return None

    def unlock(self, password: str) -> Fernet | None:
        """Return the cipher if the password is right, else None."""
        data_key = self._unwrap(password)
        return Fernet(data_key) if data_key else None

    def change_password(self, password: str, new_password: str) -> Fernet | None:
        """Re-wrap the data key under a new password. None if `password` is wrong."""
        data_key = self._unwrap(password)
        if data_key is None:
            return None
        self._write(data_key, new_password)
        return Fernet(data_key)


class GroupVault:
    """Encryption key of one group chat.

    A group has no password (a chat would show it to everyone). Instead its
    random data key is wrapped once per *key holder* with that person's
    personal data key, so a holder unlocking their own vault also opens the
    group. Nothing readable is stored: without a holder's password the group's
    files cannot be opened, not even by whoever runs the server.
    """

    def __init__(self, group_dir: Path):
        self.dir = group_dir
        self.path = group_dir / META_NAME

    def exists(self) -> bool:
        return self.path.exists()

    def _slots(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8")).get("slots", {})

    def _write(self, slots: dict[str, str]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps({"v": 1, "slots": slots}), encoding="utf-8")
        tmp.replace(self.path)

    def holders(self) -> list[int]:
        return [int(uid) for uid in self._slots()]

    def create(self, holder: int, holder_cipher: Fernet) -> bytes:
        """Set up a new group. Returns the group's data key."""
        data_key = Fernet.generate_key()
        self._write({str(holder): holder_cipher.encrypt(data_key).decode()})
        return data_key

    def unlock(self, holder: int, holder_cipher: Fernet) -> bytes | None:
        """The group's data key if `holder` holds a slot their key can open, else None."""
        token = self._slots().get(str(holder))
        if token is None:
            return None
        try:
            return holder_cipher.decrypt(token.encode())
        except InvalidToken:
            return None

    def add_holder(self, holder: int, holder_cipher: Fernet, data_key: bytes) -> None:
        slots = self._slots()
        slots[str(holder)] = holder_cipher.encrypt(data_key).decode()
        self._write(slots)

    def remove_holder(self, holder: int) -> int:
        """Drop a holder's slot. Returns how many holders are left."""
        slots = self._slots()
        slots.pop(str(holder), None)
        self._write(slots)
        return len(slots)
