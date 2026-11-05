"""Сборка системы: имитатор сервиса, детектор, база знаний, модель, политика, оркестратор."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sentinel.agent import Orchestrator, Run, Verifier
from sentinel.audit import AuditStore
from sentinel.config import Settings
from sentinel.detector import AnomalyModel, Detector
from sentinel.knowledge import Embedder, HybridRetriever, Runbook, ensure_valid, load_runbooks
from sentinel.llm import LLMClient, StubLLM
from sentinel.policy import PolicyEngine
from sentinel.service import ServiceSimulator
from sentinel.tools import Executor, default_registry

DEFAULT_RUNBOOKS = Path(__file__).resolve().parents[2] / "knowledge" / "runbooks"


@dataclass
class System:
    sim: ServiceSimulator
    detector: Detector
    orchestrator: Orchestrator
    store: AuditStore
    cfg: Settings

    def tick(self) -> Run | None:
        """Один шаг: измерение, обнаружение и (при инциденте) полная обработка."""
        self.sim.advance(self.cfg.period_s)
        window = self.sim.samples(self.cfg.slope_window)
        incident = self.detector.step(window, self.sim.logs(self.cfg.log_window_s))
        if incident is None:
            return None
        return self.orchestrator.handle(incident, window, self.sim.logs(self.cfg.log_window_s))

    def run_until_incident(self, max_ticks: int = 60) -> Run | None:
        for _ in range(max_ticks):
            run = self.tick()
            if run is not None:
                return run
        return None


def build_system(llm: LLMClient | None = None, mode: str = "hybrid", approver=None,
                 runbooks_dir: str | Path = DEFAULT_RUNBOOKS, seed: int = 7, anomaly: bool = True,
                 cfg: Settings | None = None, store: AuditStore | None = None,
                 embedder: Embedder | None = None, runbooks: list[Runbook] | None = None) -> System:
    """Собрать систему; база знаний проверяется на согласованность со словарями до запуска."""
    cfg = cfg or Settings()
    sim = ServiceSimulator(seed=seed, period_s=cfg.period_s)
    sim.advance(cfg.period_s * 400)                         # нормальная работа: обучающая выборка
    model = None
    if anomaly:
        model = AnomalyModel(quantile=cfg.anomaly_quantile).fit(sim.samples(400))
    detector = Detector(sim.name, cfg, model)
    registry = default_registry()
    kb = ensure_valid(load_runbooks(runbooks_dir) if runbooks is None else runbooks, registry)
    store = store or AuditStore()
    orch = Orchestrator(
        sim, HybridRetriever(kb, embedder=embedder, cfg=cfg), llm or StubLLM(),
        PolicyEngine(registry, cfg), Executor(sim, registry, store), Verifier(registry, cfg), store,
        cfg=cfg, mode=mode, approver=approver, on_close=lambda inc: detector.release(inc.signature))
    return System(sim, detector, orch, store, cfg)
