"""Детектор инцидентов: продукционные правила D1--D5, отсечение выбросов, статистический запасной путь D6."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sentinel.config import Settings
from sentinel.detector.anomaly import AnomalyModel
from sentinel.detector.signals import SignalExtractor
from sentinel.domain import (
    CONSUMER_STALLED,
    ERROR_RATE_HIGH,
    LATENCY_HIGH,
    LOG_SENSITIVE_DATA,
    QUEUE_GROWING,
    WORKERS_DOWN,
    Incident,
    LogLine,
    Sample,
)


@dataclass(frozen=True)
class DetectionRule:
    id: str
    required: frozenset
    forbidden: frozenset = frozenset()
    debounce: int | None = None      # None --- брать k из настроек

    def matches(self, signals: frozenset) -> bool:
        return self.required <= signals and not (self.forbidden & signals)


RULES = (
    DetectionRule("D5", frozenset({LOG_SENSITIVE_DATA}), debounce=1),
    DetectionRule("D1", frozenset({WORKERS_DOWN, QUEUE_GROWING})),
    DetectionRule("D4", frozenset({CONSUMER_STALLED, QUEUE_GROWING})),
    DetectionRule("D2", frozenset({QUEUE_GROWING, LATENCY_HIGH}),
                  forbidden=frozenset({WORKERS_DOWN, CONSUMER_STALLED})),
    DetectionRule("D3", frozenset({ERROR_RATE_HIGH})),
)


class Detector:
    def __init__(self, service: str, cfg: Settings | None = None,
                 anomaly: AnomalyModel | None = None) -> None:
        self.service = service
        self.cfg = cfg or Settings()
        self.extractor = SignalExtractor(self.cfg)
        self.anomaly = anomaly
        self._streak: dict[str, int] = {}
        self._open: set[str] = set()
        self._counter = 0

    def release(self, signature: str) -> None:
        """Вызывается после закрытия инцидента: допускает новый инцидент с той же подписью."""
        self._open.discard(signature)

    def step(self, samples: list[Sample], logs: list[LogLine]) -> Incident | None:
        signals = self.extractor.extract(samples, logs)
        matched = next((r for r in RULES if r.matches(signals)), None)
        # серии подряд идущих измерений ведутся по каждому правилу и по аномалии
        for rule in RULES:
            self._streak[rule.id] = self._streak.get(rule.id, 0) + 1 if rule.matches(signals) else 0
        incident = None
        if matched and self._streak[matched.id] >= (matched.debounce or self.cfg.debounce_k):
            incident = self._make(matched.id, "rule", signals, samples[-1].t)
        elif not matched and self.anomaly and len(samples) >= self.cfg.slope_window:
            hit = self.anomaly.is_anomaly(samples[-self.cfg.slope_window:])
            self._streak["D6"] = self._streak.get("D6", 0) + 1 if hit else 0
            if self._streak["D6"] >= self.cfg.debounce_k:
                incident = self._make("D6", "anomaly", signals, samples[-1].t)
        return incident

    def _make(self, rule: str, source: str, signals: frozenset, t: float) -> Incident | None:
        signature = hashlib.sha1(
            (self.service + "|" + ",".join(sorted(signals))).encode()).hexdigest()[:12]
        if signature in self._open:
            return None
        self._open.add(signature)
        self._counter += 1
        return Incident(f"INC-{self._counter:04d}", self.service, signals, rule, source, t, signature)
