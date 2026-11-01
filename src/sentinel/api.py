"""REST-интерфейс дежурного (точка интеграции И10): список инцидентов, карточка, подтверждение."""
from __future__ import annotations

import os
import re
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException

from sentinel.audit import build_report
from sentinel.service import FAULTS
from sentinel.system import System, build_system

LABEL = re.compile(r"^[a-z0-9._-]{1,64}$")
RESERVED_LABELS = frozenset({"auto", "system", "oncall", "detector", "policy", "executor"})


def create_app(system: System | None = None, token: str | None = None, dev: bool | None = None) -> FastAPI:
    """Все маршруты, кроме /health, требуют токен дежурного (``Authorization: Bearer``).

    Токен берётся из аргумента или переменной ``SENTINEL_API_TOKEN``. Маршруты ``/demo/*`` доступны
    только в режиме разработки (``dev=True`` или ``SENTINEL_DEV=1``). Без токена приложение не стартует.
    """
    token = token or os.environ.get("SENTINEL_API_TOKEN")
    dev = dev if dev is not None else os.environ.get("SENTINEL_DEV") == "1"
    if not token:
        raise RuntimeError("SENTINEL_API_TOKEN is not set: refusing to start without authentication")
    system = system or build_system()                  # без approver: опасные действия ждут человека
    app = FastAPI(title="Sentinel", version="0.1.0")

    def oncall(authorization: str = Header(default="")) -> None:
        scheme, _, given = authorization.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(given.encode(), token.encode()):
            raise HTTPException(401, "invalid or missing token", headers={"WWW-Authenticate": "Bearer"})

    def card(run):
        inc = run.incident
        return {"id": inc.id, "state": run.state.value, "rule": inc.rule, "source": inc.source,
                "signals": sorted(inc.signals), "reason": run.reason,
                "pending": None if run.current is None or run.state.value != "AWAITING_APPROVAL" else {
                    "action": run.current.hypothesis.action.name,
                    "params": run.current.hypothesis.action.params,
                    "confidence": round(run.current.confidence, 3),
                    "runbook": run.current.hypothesis.runbook_id}}

    @app.get("/health")
    def health():
        return {"status": "ok", "time": system.sim.now()}

    @app.get("/incidents", dependencies=[Depends(oncall)])
    def incidents():
        return [card(r) for r in system.orchestrator.runs.values()]

    @app.get("/incidents/{incident_id}", dependencies=[Depends(oncall)])
    def incident(incident_id: str):
        run = system.orchestrator.runs.get(incident_id)
        if run is None:
            raise HTTPException(404, "incident not found")
        return {**card(run), "audit": [e.__dict__ for e in system.store.events(incident_id)],
                "report": build_report(system.store, incident_id)}

    @app.post("/incidents/{incident_id}/{decision}", dependencies=[Depends(oncall)])
    def decide(incident_id: str, decision: str, x_approver: str | None = Header(default=None)):
        # Личность определяется токеном (один общий токен дежурного); X-Approver --- лишь пометка.
        if x_approver is not None and (not LABEL.fullmatch(x_approver) or x_approver in RESERVED_LABELS):
            raise HTTPException(400, "X-Approver must match ^[a-z0-9._-]{1,64}$ and not be a reserved name")
        if decision not in ("approve", "reject"):
            raise HTTPException(404, "unknown decision")
        run = system.orchestrator.runs.get(incident_id)
        if run is None:
            raise HTTPException(404, "incident not found")
        if run.state.value != "AWAITING_APPROVAL":
            raise HTTPException(409, "incident is not awaiting approval")
        return card(system.orchestrator.decide_approval(incident_id, decision == "approve", "oncall", x_approver))

    @app.post("/demo/faults/{fault}", dependencies=[Depends(oncall)])
    def inject(fault: str):
        if not dev:
            raise HTTPException(404, "demo routes are disabled")
        if fault not in FAULTS:
            raise HTTPException(404, f"unknown fault, expected one of {FAULTS}")
        system.sim.inject(fault)
        return {"injected": fault}

    @app.post("/demo/tick", dependencies=[Depends(oncall)])
    def tick(n: int = 1):
        if not dev:
            raise HTTPException(404, "demo routes are disabled")
        opened = [card(r) for r in (system.tick() for _ in range(min(n, 200))) if r is not None]
        return {"time": system.sim.now(), "incidents": opened}

    return app
