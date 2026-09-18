"""A single content-addressed object directory; every read checks its address."""
import hashlib
import os
from pathlib import Path
import re
import tempfile


class StoreError(Exception):
    """Local storage failure, never a computation verdict."""


def hex_hash(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("expected a lowercase SHA-256 hash")
    return value


class Store:
    def __init__(self, path):
        self.path = Path(path)

    def put(self, raw):
        if not isinstance(raw, bytes):
            raise TypeError("objects must be bytes")
        h = hashlib.sha256(raw).hexdigest()
        self.path.mkdir(parents=True, exist_ok=True)
        # Publish complete objects atomically; identical hashes mean identical bytes.
        fd, tmp = tempfile.mkstemp(prefix=".write-", dir=self.path)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
            os.replace(tmp, self.path / h)
        finally:
            Path(tmp).unlink(missing_ok=True)
        return h

    def get(self, h):
        """Kernel interface: bytes hash -> bytes or None; corruption raises."""
        if not isinstance(h, bytes) or len(h) != 32:
            raise ValueError("expected a 32-byte hash")
        try:
            raw = (self.path / h.hex()).read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StoreError("cannot read object") from exc
        if hashlib.sha256(raw).digest() != h:
            raise StoreError("CAS key mismatch")
        return raw

    def read(self, h):
        raw = self.get(bytes.fromhex(hex_hash(h)))
        if raw is None:
            raise StoreError("object missing")
        return raw
