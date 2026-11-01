"""Журнал аудита и таблица исполнений (SQLite; подмножество логической модели из рисунка 2.5)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL, seq INTEGER NOT NULL, ts REAL NOT NULL,
    actor TEXT NOT NULL, type TEXT NOT NULL, payload TEXT NOT NULL,
    prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS executions (
    idem_key TEXT PRIMARY KEY, incident_id TEXT NOT NULL, action TEXT NOT NULL,
    status TEXT NOT NULL, result TEXT, started_at REAL NOT NULL
);
"""


@dataclass(frozen=True)
class AuditEvent:
    incident_id: str
    seq: int
    ts: float
    actor: str
    type: str
    payload: dict
    hash: str


class AuditStore:
    def __init__(self, path: str = ":memory:") -> None:
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)

    @staticmethod
    def _digest(prev: str, incident_id: str, seq: int, ts: float, actor: str, typ: str, payload: str) -> str:
        return hashlib.sha256("|".join([prev, incident_id, str(seq), f"{ts:.3f}", actor, typ, payload]).encode()
                              ).hexdigest()

    def append(self, incident_id: str, actor: str, typ: str, payload: dict, ts: float) -> None:
        row = self.db.execute("SELECT seq, hash FROM audit_events WHERE incident_id=? ORDER BY seq DESC LIMIT 1",
                              (incident_id,)).fetchone()
        seq, prev = (row[0] + 1, row[1]) if row else (1, "")
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        digest = self._digest(prev, incident_id, seq, ts, actor, typ, body)
        self.db.execute("INSERT INTO audit_events(incident_id, seq, ts, actor, type, payload, prev_hash, hash) "
                        "VALUES (?,?,?,?,?,?,?,?)", (incident_id, seq, ts, actor, typ, body, prev, digest))
        self.db.commit()

    def events(self, incident_id: str) -> list[AuditEvent]:
        rows = self.db.execute("SELECT incident_id, seq, ts, actor, type, payload, hash FROM audit_events "
                               "WHERE incident_id=? ORDER BY seq", (incident_id,)).fetchall()
        return [AuditEvent(r[0], r[1], r[2], r[3], r[4], json.loads(r[5]), r[6]) for r in rows]

    def verify_chain(self, incident_id: str) -> bool:
        prev = ""
        for r in self.db.execute("SELECT incident_id, seq, ts, actor, type, payload, prev_hash, hash "
                                 "FROM audit_events WHERE incident_id=? ORDER BY seq", (incident_id,)):
            if r[6] != prev or self._digest(prev, r[0], r[1], r[2], r[3], r[4], r[5]) != r[7]:
                return False
            prev = r[7]
        return True

    def reserve_execution(self, key: str, incident_id: str, action: str, ts: float) -> bool:
        try:
            self.db.execute("INSERT INTO executions(idem_key, incident_id, action, status, started_at) "
                            "VALUES (?,?,?,?,?)", (key, incident_id, action, "started", ts))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def finish_execution(self, key: str, status: str, result: dict) -> None:
        self.db.execute("UPDATE executions SET status=?, result=? WHERE idem_key=?",
                        (status, json.dumps(result, default=str), key))
        self.db.commit()

    def executed_actions(self, incident_id: str) -> list[str]:
        return [r[0] for r in self.db.execute(
            "SELECT action FROM executions WHERE incident_id=? AND status='ok' ORDER BY started_at", (incident_id,))]
