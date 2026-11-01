"""Оркестратор: агентный цикл обработки инцидента (блок-схема, рисунок 2.6)."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from sentinel.agent.context import build_context
from sentinel.agent.state import StateMachine
from sentinel.agent.verifier import Verifier
from sentinel.audit.store import AuditStore
from sentinel.config import Settings
from sentinel.detector.signals import SignalExtractor, queue_slope
from sentinel.domain import (
    ActionProposal,
    Hypothesis,
    Incident,
    IncidentContext,
    ScoredHypothesis,
    State,
    Verdict,
)
from sentinel.knowledge.retriever import HybridRetriever, Retrieved
from sentinel.knowledge.symptoms import SYMPTOMS
from sentinel.llm.client import LLMClient, LLMError
from sentinel.llm.prompt import RESPONSE_SCHEMA, ResponseError, build_messages, parse_response
from sentinel.policy.engine import PolicyEngine
from sentinel.service import ServiceAdapter
from sentinel.tools.executor import Executor

Approver = Callable[[Incident, ScoredHypothesis], bool]


@dataclass
class Run:
    incident: Incident
    fsm: StateMachine = field(default_factory=StateMachine)
    queue: list = field(default_factory=list)       # оставшиеся проверенные гипотезы
    attempts: int = 0
    last_attempt_t: float | None = None
    current: ScoredHypothesis | None = None
    context: IncidentContext | None = None
    reason: str = ""

    @property
    def state(self) -> State:
        return self.fsm.state


class Orchestrator:
    def __init__(self, service: ServiceAdapter, retriever: HybridRetriever, llm: LLMClient | None,
                 policy: PolicyEngine, executor: Executor, verifier: Verifier, store: AuditStore,
                 cfg: Settings | None = None, mode: str = "hybrid", approver: Approver | None = None,
                 on_close: Callable[[Incident], None] | None = None) -> None:
        if mode not in ("hybrid", "rules_only"):
            raise ValueError(f"unknown mode: {mode}")
        self.service, self.retriever, self.llm = service, retriever, llm
        self.policy, self.executor, self.verifier, self.store = policy, executor, verifier, store
        self.cfg, self.mode, self.approver, self.on_close = cfg or Settings(), mode, approver, on_close
        self.extractor = SignalExtractor(self.cfg)
        self.runs: dict[str, Run] = {}

    # --- публичный интерфейс -----------------------------------------------------------------
    def handle(self, incident: Incident, samples: list, logs: list) -> Run:
        run = Run(incident)
        self.runs[incident.id] = run
        self._audit(run, "detector", "incident_opened", {
            "rule": incident.rule, "source": incident.source, "signals": sorted(incident.signals)})
        self._to(run, State.DIAGNOSING)
        run.context = build_context(incident, samples, logs, incident.signals, self.cfg)
        retrieved = self.retriever.search(self._query(run.context), incident.signals, incident.service)
        self._audit(run, "retrieval", "retrieved", {
            "runbooks": [(r.runbook.id, round(r.s_ret, 3)) for r in retrieved]})
        if not retrieved:
            return self._escalate(run, "no_knowledge")
        hypotheses = self._diagnose(run, retrieved)
        if hypotheses is None:
            return run
        scored = []
        for h in hypotheses:
            v = self.verifier.check(h, retrieved, incident.signals)
            self._audit(run, "verifier", "verified", {
                "runbook": h.runbook_id, "action": h.action.name, "ok": v.ok, "failed": list(v.failed),
                "confidence": round(v.scored.confidence, 3) if v.scored else None})
            if v.ok:
                scored.append(v.scored)
        run.queue = sorted(scored, key=lambda s: -s.confidence)
        if not run.queue:
            return self._escalate(run, "all_hypotheses_rejected")
        self._to(run, State.PLANNED)
        return self._plan_and_act(run)

    def decide_approval(self, incident_id: str, approve: bool, approver: str = "oncall",
                        label: str | None = None) -> Run:
        """Решение дежурного по ожидающему подтверждения инциденту.

        ``approver`` --- аутентифицированный субъект (задаётся сервером), ``label`` --- необязательная
        самостоятельно заявленная метка; в журнале они хранятся раздельно.
        """
        run = self.runs[incident_id]
        if run.state is not State.AWAITING_APPROVAL:
            raise RuntimeError(f"{incident_id} is not awaiting approval")
        self._audit(run, f"human:{approver}", "approval", {"approved": approve, "label": label})
        if not approve:
            return self._escalate(run, "approval_rejected")
        run = self._act(run)
        return self._plan_and_act(run) if run.state is State.PLANNED else run

    # --- этапы -------------------------------------------------------------------------------------------
    def _query(self, ctx: IncidentContext) -> str:
        phrases = [SYMPTOMS[s] for s in sorted(ctx.signals) if s in SYMPTOMS]
        lines = [re.sub(r"\d+", "#", line) for line in ctx.logs[-3:] if not line.startswith("INFO")]
        return " ".join(sorted(ctx.signals) + phrases + lines)

    def _diagnose(self, run: Run, retrieved: list[Retrieved]) -> list[Hypothesis] | None:
        if self.mode == "rules_only":
            return self._symbolic_hypotheses(run, retrieved)
        error = ""
        for attempt in range(self.cfg.llm_retries + 1):
            system, user = build_messages(run.context, retrieved, error)
            try:
                text = self.llm.complete(system, user, RESPONSE_SCHEMA)
                hyps = parse_response(text, self.cfg)
                self._audit(run, "llm", "llm_response", {"attempt": attempt + 1, "hypotheses": len(hyps)})
                if not hyps:
                    self._escalate(run, "insufficient_data")
                    return None
                return hyps
            except LLMError as exc:
                self._audit(run, "llm", "llm_error", {"error": str(exc)})
                self._escalate(run, "llm_unavailable")                        # К5
                return None
            except ResponseError as exc:
                error = str(exc)
                self._audit(run, "llm", "llm_invalid", {"attempt": attempt + 1, "error": error})
        self._escalate(run, "llm_invalid_response")                            # К5
        return None

    def _symbolic_hypotheses(self, run: Run, retrieved: list[Retrieved]) -> list[Hypothesis]:
        """Режим сравнения rules_only: диагноз без модели --- лучшее совпадение с инструкцией."""
        out = []
        for r in retrieved:
            required = set(r.runbook.signals_required)
            m = len(required & run.incident.signals) / len(required) if required else 0.0
            out.append(Hypothesis(r.runbook.id, r.runbook.title, "совпадение сигналов с инструкцией",
                                  ActionProposal(r.runbook.actions[0], self._default_params(r.runbook.actions[0])),
                                  m))
        return out

    @staticmethod
    def _default_params(action: str) -> dict:
        return {"scale_workers": {"delta": 2}, "purge_queue": {"queue": "default"}}.get(action, {})

    def _plan_and_act(self, run: Run) -> Run:
        while True:
            if not run.queue or run.attempts >= self.cfg.max_attempts:
                return self._escalate(run, "hypotheses_exhausted")
            sh = run.queue.pop(0)
            run.current = sh
            since = None if run.last_attempt_t is None else self.service.now() - run.last_attempt_t
            decision = self.policy.evaluate(sh.hypothesis.action, sh.confidence, run.incident.signals,
                                            run.attempts, since)
            self._audit(run, "policy", "decision", {
                "action": sh.hypothesis.action.name, "verdict": decision.verdict.name,
                "fired": list(decision.fired), "confidence": round(sh.confidence, 3)})
            if decision.verdict is Verdict.AUTO_EXECUTE:
                result = self._act(run)
            elif decision.verdict is Verdict.REQUIRE_APPROVAL:
                self._to(run, State.AWAITING_APPROVAL)
                if self.approver is None:
                    return run                                           # ждём решения дежурного
                approved = self.approver(run.incident, sh)
                self._audit(run, "human:auto", "approval", {"approved": approved})
                result = self._act(run) if approved else self._escalate(run, "approval_rejected")
            else:
                return self._escalate(run, f"policy_{decision.verdict.name.lower()}")
            if result.state is not State.PLANNED:
                return result

    def _act(self, run: Run) -> Run:
        sh = run.current
        action = sh.hypothesis.action
        self._to(run, State.ACTING)
        run.attempts += 1
        run.last_attempt_t = self.service.now()
        res = self.executor.execute(run.incident.id, action.name, action.params, run.attempts)
        self._audit(run, "executor", "executed", {"action": action.name, "status": res.status,
                                                  "detail": res.detail})
        if res.status == "failed":
            return self._escalate(run, "execution_failed")
        self._to(run, State.VERIFYING)
        if self._verify_result(run, sh):
            self._to(run, State.RESOLVED)
            self._audit(run, "system", "resolved", {})
            self._close(run)
            return run
        if run.queue and run.attempts < self.cfg.max_attempts:
            self._to(run, State.PLANNED)                                  # следующая гипотеза (К8)
            return run
        return self._escalate(run, "result_not_confirmed")

    def _verify_result(self, run: Run, sh: ScoredHypothesis) -> bool:
        rb = next(r for r in self.retriever.runbooks if r.id == sh.hypothesis.runbook_id)
        if not rb.success_criteria:
            return False                                                   # автоматически подтвердить нечем
        self.service.advance(self.cfg.verify_wait_s)
        # две последовательные проверки: окна, заканчивающиеся на двух последних измерениях
        window = self.cfg.slope_window
        samples = self.service.samples(window + self.cfg.verify_consecutive - 1)
        logs = self.service.logs(self.cfg.log_window_s)
        ok = True
        for i in range(self.cfg.verify_consecutive):
            end = len(samples) - (self.cfg.verify_consecutive - 1 - i)
            win = samples[max(0, end - window):end]
            signals = self.extractor.extract(win, logs)
            ok = ok and all(_criterion(c, signals, win) for c in rb.success_criteria)
        self._audit(run, "verify", "result_check", {"criteria": list(rb.success_criteria), "ok": ok})
        return ok

    def _escalate(self, run: Run, reason: str) -> Run:
        run.reason = reason
        inc = run.incident
        for action, params in (("create_ticket", {"title": f"{inc.id}: {reason}",
                                                  "body": f"signals={sorted(inc.signals)}"}),
                               ("notify_oncall", {"message": f"{inc.id} escalated: {reason}"})):
            res = self.executor.execute(inc.id, action, params, attempt=0)
            self._audit(run, "executor", "escalation_action", {"action": action, "status": res.status})
        self._to(run, State.ESCALATED)
        self._audit(run, "system", "escalated", {"reason": reason})
        self._close(run)
        return run

    # --- служебное -----------------------------------------------------------------------------------------
    def _close(self, run: Run) -> None:
        if self.on_close:
            self.on_close(run.incident)

    def _to(self, run: Run, new: State) -> None:
        old = run.state
        run.fsm.to(new)
        self._audit(run, "system", "state", {"from": old.value, "to": new.value})

    def _audit(self, run: Run, actor: str, typ: str, payload: dict) -> None:
        self.store.append(run.incident.id, actor, typ, payload, self.service.now())


def _criterion(crit: str, signals: frozenset, window: list) -> bool:
    """Предикаты критериев успеха: ``X``, ``not X``, ``queue_slope < N``, ``queue_len < N``."""
    crit = crit.strip()
    m = re.fullmatch(r"(queue_slope|queue_len)\s*(<=|<)\s*(-?\d+(?:\.\d+)?)", crit)
    if m:
        value = queue_slope(window) if m.group(1) == "queue_slope" else window[-1].queue_len
        limit = float(m.group(3))
        return value <= limit if m.group(2) == "<=" else value < limit
    if crit.startswith("not "):
        return crit[4:].strip() not in signals
    return crit in signals
