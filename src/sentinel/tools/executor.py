"""Исполнитель: идемпотентный вызов действия из реестра."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sentinel.audit.store import AuditStore
from sentinel.service import ServiceAdapter
from sentinel.tools.registry import ActionRegistry


def idempotency_key(incident_id: str, action: str, params: dict, attempt: int) -> str:
    canon = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{incident_id}|{action}|{canon}|{attempt}".encode()).hexdigest()


@dataclass(frozen=True)
class ExecResult:
    status: str           # "ok" | "failed" | "duplicate"
    key: str
    detail: dict


class Executor:
    def __init__(self, backend: ServiceAdapter, registry: ActionRegistry, store: AuditStore) -> None:
        self.backend, self.registry, self.store = backend, registry, store

    def execute(self, incident_id: str, action: str, params: dict, attempt: int) -> ExecResult:
        violation = self.registry.validate(action, params)
        if violation:
            return ExecResult("failed", "", {"error": violation})
        key = idempotency_key(incident_id, action, params, attempt)
        if not self.store.reserve_execution(key, incident_id, action, self.backend.now()):
            return ExecResult("duplicate", key, {})       # повторная доставка: действие не повторяется
        try:
            detail = self.backend.execute(action, params)
        except Exception as exc:  # noqa: BLE001 - любой сбой backend фиксируется в аудите
            self.store.finish_execution(key, "failed", {"error": str(exc)})
            return ExecResult("failed", key, {"error": str(exc)})
        status = "ok" if detail.get("ok") else "failed"
        self.store.finish_execution(key, status, detail)
        return ExecResult(status, key, detail)
