"""Предметные типы: единая система идентификаторов и структуры обмена между компонентами."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum

# --- словарь сигналов -------------------------------------------------------------
WORKERS_DOWN = "WORKERS_DOWN"
QUEUE_GROWING = "QUEUE_GROWING"
LATENCY_HIGH = "LATENCY_HIGH"
ERROR_RATE_HIGH = "ERROR_RATE_HIGH"
CONSUMER_STALLED = "CONSUMER_STALLED"
LOG_DB_CONN = "LOG_DB_CONN"
LOG_SENSITIVE_DATA = "LOG_SENSITIVE_DATA"
LOG_INJECTION_SUSPECT = "LOG_INJECTION_SUSPECT"

SIGNALS = frozenset(
    {WORKERS_DOWN, QUEUE_GROWING, LATENCY_HIGH, ERROR_RATE_HIGH, CONSUMER_STALLED,
     LOG_DB_CONN, LOG_SENSITIVE_DATA, LOG_INJECTION_SUSPECT}
)


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Verdict(IntEnum):
    """Порядок значений задаёт строгость: итоговый вердикт --- максимум."""

    AUTO_EXECUTE = 0
    REQUIRE_APPROVAL = 1
    ESCALATE = 2
    DENY = 3


class State(str, Enum):
    NEW = "NEW"
    DIAGNOSING = "DIAGNOSING"
    PLANNED = "PLANNED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    ACTING = "ACTING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


FINAL_STATES = frozenset({State.RESOLVED, State.ESCALATED})


@dataclass(frozen=True)
class Sample:
    """Одно измерение метрик демо-сервиса."""

    t: float
    queue_len: float
    workers_alive: int
    error_rate: float
    p95_ms: float
    processed_rate: float
    arrival_rate: float


@dataclass(frozen=True)
class LogLine:
    t: float
    level: str
    text: str


@dataclass(frozen=True)
class Incident:
    id: str
    service: str
    signals: frozenset
    rule: str              # D1..D5 либо D6 (аномалия)
    source: str            # "rule" | "anomaly"
    opened_at: float
    signature: str


@dataclass
class IncidentContext:
    incident: Incident
    samples: list
    logs: list             # очищенные строки: недоверенные данные
    signals: frozenset
    injection_suspect: bool = False


@dataclass(frozen=True)
class ActionProposal:
    name: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Hypothesis:
    runbook_id: str
    cause: str
    explanation: str
    action: ActionProposal
    confidence_llm: float


@dataclass(frozen=True)
class ScoredHypothesis:
    hypothesis: Hypothesis
    s_ret: float
    m_sig: float
    confidence: float
