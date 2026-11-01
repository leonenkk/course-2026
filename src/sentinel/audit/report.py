"""Постмортем по журналу аудита."""
from __future__ import annotations

from sentinel.audit.store import AuditStore


def build_report(store: AuditStore, incident_id: str) -> str:
    lines = [f"# Отчёт по инциденту {incident_id}", ""]
    for e in store.events(incident_id):
        lines.append(f"{e.seq:>2}. [{e.ts:7.1f}] {e.actor:<9} {e.type:<18} {e.payload}")
    lines += ["", f"Целостность журнала: {'подтверждена' if store.verify_chain(incident_id) else 'НАРУШЕНА'}"]
    return "\n".join(lines)
