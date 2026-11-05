"""REST-интерфейс и веб-панель дежурного (точка интеграции И10).

Все маршруты данных, кроме ``/health`` и статической страницы ``/``, требуют токен дежурного
(``Authorization: Bearer``). Страница не содержит данных и секретов: токен вводит человек, данные
приходят через те же защищённые маршруты. Состояние системы общее для потоков сервера, поэтому все
обращения к нему сериализуются блокировкой.
"""
from __future__ import annotations

import os
import re
import secrets
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

from sentinel.audit import build_report
from sentinel.domain import State
from sentinel.service import FAULTS
from sentinel.system import System, build_system

LABEL = re.compile(r"^[a-z0-9._-]{1,64}$")
RESERVED_LABELS = frozenset({"auto", "system", "oncall", "detector", "policy", "executor"})
PANEL = Path(__file__).with_name("web") / "index.html"
CSP = ("default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def _hypothesis(sh) -> dict | None:
    if sh is None:
        return None
    h = sh.hypothesis
    return {"runbook": h.runbook_id, "cause": h.cause, "explanation": h.explanation,
            "action": h.action.name, "params": h.action.params, "confidence": round(sh.confidence, 3),
            "c_llm": round(h.confidence_llm, 3), "s_ret": round(sh.s_ret, 3), "m_sig": round(sh.m_sig, 3)}


def card(run) -> dict:
    inc = run.incident
    pending = run.state is State.AWAITING_APPROVAL and run.current is not None
    return {"id": inc.id, "state": run.state.value, "rule": inc.rule, "source": inc.source,
            "signals": sorted(inc.signals), "reason": run.reason, "opened_at": inc.opened_at,
            "closed_at": run.closed_at, "approvals": run.approvals,
            "diagnosis": _hypothesis(run.diagnosis),
            "pending": _hypothesis(run.current) if pending else None,
            "retrieved": [{"runbook": r.runbook.id, "title": r.runbook.title, "s_ret": round(r.s_ret, 3)}
                          for r in run.retrieved],
            "timings_ms": {k: round(v, 1) for k, v in run.timings.items()}}


def create_app(system: System | None = None, token: str | None = None, dev: bool | None = None) -> FastAPI:
    """Токен берётся из аргумента или ``SENTINEL_API_TOKEN``; без него приложение не стартует.

    Маршруты ``/demo/*`` доступны только в режиме разработки (``dev=True`` или ``SENTINEL_DEV=1``).
    """
    token = token or os.environ.get("SENTINEL_API_TOKEN")
    dev = dev if dev is not None else os.environ.get("SENTINEL_DEV") == "1"
    if not token:
        raise RuntimeError("SENTINEL_API_TOKEN is not set: refusing to start without authentication")
    system = system or build_system()                  # без approver: опасные действия ждут человека
    lock = threading.RLock()
    app = FastAPI(title="Sentinel", version="0.2.0")

    def oncall(authorization: str = Header(default="")) -> None:
        scheme, _, given = authorization.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(given.encode(), token.encode()):
            raise HTTPException(401, "invalid or missing token", headers={"WWW-Authenticate": "Bearer"})

    def require_dev() -> None:
        if not dev:
            raise HTTPException(404, "demo routes are disabled")

    def get_run(incident_id: str):
        run = system.orchestrator.runs.get(incident_id)
        if run is None:
            raise HTTPException(404, "incident not found")
        return run

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def panel():
        return HTMLResponse(PANEL.read_text(encoding="utf-8"), headers={
            "Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"})

    @app.get("/health")
    def health():
        return {"status": "ok", "time": system.sim.now()}

    @app.get("/config", dependencies=[Depends(oncall)])
    def config():
        orch, cfg = system.orchestrator, system.cfg
        return {"dev": dev, "faults": list(FAULTS) if dev else [], "mode": orch.mode,
                "llm": getattr(orch.llm, "name", "unknown"),
                "embedder": getattr(orch.retriever.embedder, "name", "unknown"),
                "runbooks": len(orch.retriever.runbooks), "service": system.sim.name,
                # формула (2.4) и пороги политики P5, P6 — чтобы панель объясняла уверенность
                "weights": {"llm": cfg.w_llm, "ret": cfg.w_ret, "sig": cfg.w_sig},
                "thresholds": {"escalate": cfg.tau_esc,
                               **{f"auto_{risk.value}": tau for risk, tau in cfg.tau_auto.items()}}}

    @app.get("/incidents", dependencies=[Depends(oncall)])
    def incidents():
        with lock:
            return [card(r) for r in reversed(system.orchestrator.runs.values())]

    @app.get("/incidents/{incident_id}", dependencies=[Depends(oncall)])
    def incident(incident_id: str):
        with lock:
            run = get_run(incident_id)
            return {**card(run), "audit": [e.__dict__ for e in system.store.events(incident_id)],
                    "chain_ok": system.store.verify_chain(incident_id),
                    "report": build_report(system.store, incident_id)}

    @app.post("/incidents/{incident_id}/{decision}", dependencies=[Depends(oncall)])
    def decide(incident_id: str, decision: str, x_approver: str | None = Header(default=None)):
        # Личность определяется токеном (один общий токен дежурного); X-Approver --- лишь пометка.
        if x_approver is not None and (not LABEL.fullmatch(x_approver) or x_approver in RESERVED_LABELS):
            raise HTTPException(400, "X-Approver must match ^[a-z0-9._-]{1,64}$ and not be a reserved name")
        if decision not in ("approve", "reject"):
            raise HTTPException(404, "unknown decision")
        with lock:
            run = get_run(incident_id)
            if run.state is not State.AWAITING_APPROVAL:
                raise HTTPException(409, "incident is not awaiting approval")
            return card(system.orchestrator.decide_approval(incident_id, decision == "approve", "oncall",
                                                            x_approver))

    @app.post("/demo/faults/{fault}", dependencies=[Depends(oncall), Depends(require_dev)])
    def inject(fault: str):
        if fault not in FAULTS:
            raise HTTPException(404, f"unknown fault, expected one of {FAULTS}")
        with lock:
            system.sim.inject(fault)
        return {"injected": fault}

    @app.post("/demo/tick", dependencies=[Depends(oncall), Depends(require_dev)])
    def tick(n: int = 1):
        with lock:
            opened = [card(r) for r in (system.tick() for _ in range(max(1, min(n, 200)))) if r is not None]
            return {"time": system.sim.now(), "incidents": opened}

    return app
