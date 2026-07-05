"""In-memory session store for uploaded data (dev/demo).

Keeps the parsed long frame per session_id so /forecast, /simulate and /explain
can run against an upload without re-sending the CSVs. For production this would
swap to GCS/Firebase (documented in the roadmap); the interface is intentionally
tiny so that swap is local.
"""
from __future__ import annotations

import threading
import time
import uuid

import pandas as pd


class SessionStore:
    def __init__(self, ttl_seconds: int = 60 * 60 * 6):
        self._data: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def create(self, long_df: pd.DataFrame, summary: dict) -> str:
        sid = uuid.uuid4().hex[:12]
        with self._lock:
            self._data[sid] = {"long": long_df, "summary": summary,
                               "ts": time.time()}
        self._gc()
        return sid

    def get(self, sid: str) -> pd.DataFrame:
        with self._lock:
            entry = self._data.get(sid)
        if entry is None:
            raise KeyError(sid)
        return entry["long"]

    def _gc(self):
        now = time.time()
        with self._lock:
            stale = [k for k, v in self._data.items() if now - v["ts"] > self._ttl]
            for k in stale:
                del self._data[k]


STORE = SessionStore()
