"""Верификатор: проверки V2--V5 и расчёт итоговой уверенности (формула 2.4)."""
from __future__ import annotations

from dataclasses import dataclass

from sentinel.config import Settings
from sentinel.domain import Hypothesis, ScoredHypothesis
from sentinel.knowledge.retriever import Retrieved
from sentinel.tools.registry import ActionRegistry


def confidence(c_llm: float, s_ret: float, m_sig: float, cfg: Settings | None = None) -> float:
    cfg = cfg or Settings()
    return cfg.w_llm * c_llm + cfg.w_ret * s_ret + cfg.w_sig * m_sig


@dataclass(frozen=True)
class Verification:
    ok: bool
    failed: tuple                    # идентификаторы непройденных проверок
    scored: ScoredHypothesis | None


class Verifier:
    def __init__(self, registry: ActionRegistry, cfg: Settings | None = None) -> None:
        self.registry = registry
        self.cfg = cfg or Settings()

    def check(self, hyp: Hypothesis, retrieved: list[Retrieved], observed: frozenset) -> Verification:
        failed: list[str] = []
        by_id = {r.runbook.id: r for r in retrieved}
        found = by_id.get(hyp.runbook_id)
        if found is None:                                                    # V2: привязка к источнику
            return Verification(False, ("V2",), None)
        rb = found.runbook
        if hyp.action.name not in rb.actions:                                # V3: действие из перечня
            failed.append("V3")
        required = set(rb.signals_required)
        m_sig = len(required & observed) / len(required) if required else 0.0
        if set(rb.signals_excluded) & observed or m_sig < self.cfg.m_min:    # V4: согласованность с сигналами
            failed.append("V4")
        if self.registry.validate(hyp.action.name, hyp.action.params):       # V5: параметры и лимиты
            failed.append("V5")
        if failed:
            return Verification(False, tuple(failed), None)
        c = confidence(hyp.confidence_llm, found.s_ret, m_sig, self.cfg)
        return Verification(True, (), ScoredHypothesis(hyp, found.s_ret, m_sig, c))
