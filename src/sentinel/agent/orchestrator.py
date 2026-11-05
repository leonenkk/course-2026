"""Оркестратор: агентный цикл обработки инцидента (блок-схема, рисунок 2.6).

Режимы (для сравнения подходов в разделе 3 записки):

- ``hybrid`` --- поиск инструкций, гипотезы модели, верификатор V2--V5 и политика P1--P7;
- ``rules_only`` --- модель не вызывается, гипотезы строятся символьным сопоставлением сигналов;
- ``llm_only`` --- модель сама выбирает инструмент без инструкций, верификатора и политики.
  Это заведомо небезопасный режим, поэтому он разрешён только на имитаторе (``service.sandbox``).
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from sentinel.agent.context import build_context
from sentinel.agent.state import StateMachine
from sentinel.agent.verifier import Verifier
from sentinel.audit.store import AuditStore
from sentinel.config import Settings
from sentinel.detector.signals import SignalExtractor
from sentinel.domain import (
    ActionProposal,
    Hypothesis,
    Incident,
    ScoredHypothesis,
    State,
    Verdict,
)
from sentinel.knowledge.criteria import holds
from sentinel.knowledge.retriever import HybridRetriever, Retrieved
from sentinel.knowledge.symptoms import SYMPTOMS
from sentinel.llm.client import LLMClient, LLMError
from sentinel.llm.prompt import (
    RESPONSE_SCHEMA,
    ResponseError,
    build_messages,
    build_messages_llm_only,
    parse_response,
)
from sentinel.policy.engine import PolicyEngine
from sentinel.service import ServiceAdapter
from sentinel.tools.executor import Executor

Approver = Callable[[Incident, ScoredHypothesis], bool]
MODES = ("hybrid", "rules_only", "llm_only")


@dataclass
class Run:
    incident: Incident
    fsm: StateMachine = field(default_factory=StateMachine)
    queue: list = field(default_factory=list)       # оставшиеся проверенные гипотезы
    attempts: int = 0
    last_attempt_t: float | None = None
    current: ScoredHypothesis | None = None
    context: object | None = None
    retrieved: list = field(default_factory=list)
    diagnosis: ScoredHypothesis | None = None       # лучшая гипотеза, прошедшая верификацию
    reason: str = ""
    approvals: int = 0                              # сколько раз потребовалось решение человека
    llm_calls: int = 0
    timings: dict = field(default_factory=dict)     # мс по этапам (настенное время)
    closed_at: float | None = None                  # время имитатора на момент закрытия

    @property
    def state(self) -> State:
        return self.fsm.state

    @property
    def active_ms(self) -> float:
        return sum(self.timings.values())


class Orchestrator:
    def __init__(self, service: ServiceAdapter, retriever: HybridRetriever, llm: LLMClient | None,
                 policy: PolicyEngine, executor: Executor, verifier: Verifier, store: AuditStore,
                 cfg: Settings | None = None, mode: str = "hybrid", approver: Approver | None = None,
                 on_close: Callable[[Incident], None] | None = None) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown mode: {mode}")
        if mode == "llm_only" and not getattr(service, "sandbox", False):
            raise ValueError("llm_only executes actions without policy and is allowed only on the simulator")
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
            "rule": incident.rule, "source": incident.source, "signals": sorted(incident.signals),
            "mode": self.mode})
        self._to(run, State.DIAGNOSING)
        with self._timed(run, "context"):
            run.context = build_context(incident, samples, logs, incident.signals, self.cfg)
        if self.mode == "llm_only":
            return self._handle_llm_only(run)

        with self._timed(run, "retrieval"):
            retrieved = self.retriever.search(self._query(run.context), incident.signals, incident.service)
        run.retrieved = retrieved
        self._audit(run, "retrieval", "retrieved", {
            "runbooks": [(r.runbook.id, round(r.s_ret, 3)) for r in retrieved],
            "degraded": self.retriever.degraded})
        if not retrieved:
            return self._escalate(run, "no_knowledge")                       # К3
        if self.mode == "rules_only":
            hypotheses = self._symbolic_hypotheses(run, retrieved)
        else:
            tools = [self.policy.registry.get(a).describe()
                     for a in dict.fromkeys(a for r in retrieved for a in r.runbook.actions)]
            hypotheses = self._ask_llm(run, lambda err: build_messages(run.context, retrieved, err, tools))
        if hypotheses is None:
            return run
        with self._timed(run, "verification"):
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
            return self._escalate(run, "all_hypotheses_rejected")             # К1, К2, К4
        run.diagnosis = run.queue[0]
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
    def _query(self, ctx) -> str:
        phrases = [SYMPTOMS[s] for s in sorted(ctx.signals) if s in SYMPTOMS]
        lines = [re.sub(r"\d+", "#", line) for line in ctx.logs[-3:] if not line.startswith("INFO")]
        return " ".join(sorted(ctx.signals) + phrases + lines)

    def _ask_llm(self, run: Run, build: Callable[[str], tuple[str, str]]) -> list[Hypothesis] | None:
        """Вызов модели с ограниченным числом повторов; None --- инцидент уже передан человеку."""
        error = ""
        for attempt in range(self.cfg.llm_retries + 1):
            if run.active_ms > self.cfg.max_active_s * 1000:
                self._escalate(run, "budget_exceeded")
                return None
            system, user = build(error)
            try:
                run.llm_calls += 1
                with self._timed(run, "llm"):
                    text = self.llm.complete(system, user, RESPONSE_SCHEMA)
                hyps = parse_response(text, self.cfg)
            except LLMError as exc:
                self._audit(run, "llm", "llm_error", {"error": str(exc)})
                self._escalate(run, "llm_unavailable")                        # К5
                return None
            except ResponseError as exc:
                error = str(exc)
                self._audit(run, "llm", "llm_invalid", {"attempt": attempt + 1, "error": error})
                continue
            self._audit(run, "llm", "llm_response", {"attempt": attempt + 1, "hypotheses": [
                {"runbook": h.runbook_id, "action": h.action.name, "params": h.action.params,
                 "confidence": h.confidence_llm, "cause": h.cause[:300]} for h in hyps]})
            if not hyps:
                self._escalate(run, "insufficient_data")
                return None
            return hyps
        self._escalate(run, "llm_invalid_response")                            # К5
        return None

    def _symbolic_hypotheses(self, run: Run, retrieved: list[Retrieved]) -> list[Hypothesis]:
        """Режим rules_only: диагноз без модели --- совпадение сигналов с каждой найденной инструкцией."""
        out = []
        for r in retrieved:
            required = set(r.runbook.signals_required)
            m = len(required & run.incident.signals) / len(required) if required else 0.0
            action = r.runbook.actions[0]
            out.append(Hypothesis(r.runbook.id, r.runbook.title, "совпадение сигналов с инструкцией",
                                  ActionProposal(action, self._default_params(action)), m))
        return out

    @staticmethod
    def _default_params(action: str) -> dict:
        return {"scale_workers": {"delta": 2}, "purge_queue": {"queue": "default"}}.get(action, {})

    def _handle_llm_only(self, run: Run) -> Run:
        registry = self.policy.registry
        tools = [registry.get(n).describe() for n in registry.names()]
        hyps = self._ask_llm(run, lambda err: build_messages_llm_only(run.context, tools, err))
        if hyps is None:
            return run
        run.queue = [ScoredHypothesis(h, 0.0, 0.0, h.confidence_llm) for h in hyps]
        run.diagnosis = run.queue[0]
        self._to(run, State.PLANNED)
        while True:
            if not run.queue or run.attempts >= self.cfg.max_attempts:
                return self._escalate(run, "hypotheses_exhausted")
            run.current = run.queue.pop(0)
            self._audit(run, "policy", "decision", {"action": run.current.hypothesis.action.name,
                                                    "verdict": "NOT_CHECKED", "fired": []})
            result = self._act(run)
            if result.state is not State.PLANNED:
                return result

    def _plan_and_act(self, run: Run) -> Run:
        while True:
            if not run.queue or run.attempts >= self.cfg.max_attempts:
                return self._escalate(run, "hypotheses_exhausted")
            sh = run.queue.pop(0)
            run.current = sh
            since = None if run.last_attempt_t is None else self.service.now() - run.last_attempt_t
            with self._timed(run, "policy"):
                decision = self.policy.evaluate(sh.hypothesis.action, sh.confidence, run.incident.signals,
                                                run.attempts, since)
            self._audit(run, "policy", "decision", {
                "action": sh.hypothesis.action.name, "verdict": decision.verdict.name,
                "fired": list(decision.fired), "confidence": round(sh.confidence, 3)})
            if decision.verdict is Verdict.AUTO_EXECUTE:
                result = self._act(run)
            elif decision.verdict is Verdict.REQUIRE_APPROVAL:
                self._to(run, State.AWAITING_APPROVAL)
                run.approvals += 1
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
        with self._timed(run, "execution"):
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

    def _success_criteria(self, run: Run, sh: ScoredHypothesis) -> tuple:
        if self.mode == "llm_only":                       # инструкций нет: исчезли исходные сигналы
            return tuple(f"not {s}" for s in sorted(run.incident.signals))
        rb = next(r for r in self.retriever.runbooks if r.id == sh.hypothesis.runbook_id)
        return rb.success_criteria

    def _verify_result(self, run: Run, sh: ScoredHypothesis) -> bool:
        criteria = self._success_criteria(run, sh)
        if not criteria:
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
            ok = ok and all(holds(c, signals, win) for c in criteria)
        self._audit(run, "verify", "result_check", {"criteria": list(criteria), "ok": ok})
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
    @contextmanager
    def _timed(self, run: Run, stage: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            run.timings[stage] = run.timings.get(stage, 0.0) + (time.perf_counter() - start) * 1000

    def _close(self, run: Run) -> None:
        run.closed_at = self.service.now()
        if self.on_close:
            self.on_close(run.incident)

    def _to(self, run: Run, new: State) -> None:
        old = run.state
        run.fsm.to(new)
        self._audit(run, "system", "state", {"from": old.value, "to": new.value})

    def _audit(self, run: Run, actor: str, typ: str, payload: dict) -> None:
        self.store.append(run.incident.id, actor, typ, payload, self.service.now())
