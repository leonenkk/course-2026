"""REST-интерфейс дежурного (точка интеграции И10): список инцидентов, карточка, подтверждение."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from sentinel.audit import build_report
from sentinel.service import FAULTS
from sentinel.system import System, build_system


def create_app(system: System | None = None) -> FastAPI:
    system = system or build_system()                  # без approver: опасные действия ждут человека
    app = FastAPI(title="Sentinel", version="0.1.0")

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

    @app.get("/incidents")
    def incidents():
        return [card(r) for r in system.orchestrator.runs.values()]

    @app.get("/incidents/{incident_id}")
    def incident(incident_id: str):
        run = system.orchestrator.runs.get(incident_id)
        if run is None:
            raise HTTPException(404, "incident not found")
        return {**card(run), "audit": [e.__dict__ for e in system.store.events(incident_id)],
                "report": build_report(system.store, incident_id)}

    @app.post("/incidents/{incident_id}/{decision}")
    def decide(incident_id: str, decision: str):
        if decision not in ("approve", "reject"):
            raise HTTPException(404, "unknown decision")
        run = system.orchestrator.runs.get(incident_id)
        if run is None:
            raise HTTPException(404, "incident not found")
        if run.state.value != "AWAITING_APPROVAL":
            raise HTTPException(409, "incident is not awaiting approval")
        return card(system.orchestrator.decide_approval(incident_id, decision == "approve"))

    @app.post("/demo/faults/{fault}")
    def inject(fault: str):
        if fault not in FAULTS:
            raise HTTPException(404, f"unknown fault, expected one of {FAULTS}")
        system.sim.inject(fault)
        return {"injected": fault}

    @app.post("/demo/tick")
    def tick(n: int = 1):
        opened = [card(r) for r in (system.tick() for _ in range(min(n, 200))) if r is not None]
        return {"time": system.sim.now(), "incidents": opened}

    return app
