"""Движок политик: правила P1--P7, итоговый вердикт --- наиболее строгий из сработавших (формула 2.5)."""
from __future__ import annotations

from dataclasses import dataclass

from sentinel.config import Settings
from sentinel.domain import LOG_INJECTION_SUSPECT, LOG_SENSITIVE_DATA, ActionProposal, Risk, Verdict
from sentinel.tools.registry import ActionRegistry


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    fired: tuple          # идентификаторы сработавших правил


class PolicyEngine:
    def __init__(self, registry: ActionRegistry, cfg: Settings | None = None) -> None:
        self.registry = registry
        self.cfg = cfg or Settings()

    def evaluate(self, proposal: ActionProposal, confidence: float, signals: frozenset,
                 attempts: int, since_last_attempt_s: float | None) -> Decision:
        cfg = self.cfg
        fired: list[tuple[str, Verdict]] = []
        violation = self.registry.validate(proposal.name, proposal.params)
        if violation:
            fired.append(("P1", Verdict.DENY))
        if LOG_SENSITIVE_DATA in signals:
            fired.append(("P2", Verdict.ESCALATE))
        if LOG_INJECTION_SUSPECT in signals:
            fired.append(("P3", Verdict.REQUIRE_APPROVAL))
        risk = self.registry.get(proposal.name).risk if proposal.name in self.registry else Risk.HIGH
        if risk is Risk.HIGH:
            fired.append(("P4", Verdict.REQUIRE_APPROVAL))
        if confidence < cfg.tau_esc:
            fired.append(("P5", Verdict.ESCALATE))
        elif risk in cfg.tau_auto and confidence < cfg.tau_auto[risk]:
            fired.append(("P6", Verdict.REQUIRE_APPROVAL))
        if attempts >= cfg.max_attempts or (
                since_last_attempt_s is not None and since_last_attempt_s < cfg.cooldown_s):
            fired.append(("P7", Verdict.ESCALATE))
        verdict = max((v for _, v in fired), default=Verdict.AUTO_EXECUTE)
        return Decision(verdict, tuple(rule for rule, _ in fired))
