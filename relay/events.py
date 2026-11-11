"""JSONL event log. One line per event; t is time.perf_counter() seconds (monotonic).

Every results table must be computable from this single file.
Event names: enqueue, admit, send, first_token, last_token, retry, giveup, shed,
degrade, tool_call, tool_timeout, step_start, step_end, done, abandon, http_429.
"""
import json
import time


class EventLog:
    def __init__(self, path: str | None):
        self.path = path
        self._f = open(path, "a", encoding="utf-8", buffering=1) if path else None
        self.t0 = time.perf_counter()

    def emit(self, req_id: str, event: str, **kw):
        rec = {"t": time.perf_counter(), "req": req_id, "event": event, **kw}
        if self._f:
            self._f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        return rec

    def close(self):
        if self._f:
            self._f.close()
