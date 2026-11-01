"""Вычисление сигналов по окну метрик и строкам логов (таблица сигналов раздела 2)."""
from __future__ import annotations

import re

from sentinel.config import Settings
from sentinel.domain import (
    CONSUMER_STALLED,
    ERROR_RATE_HIGH,
    LATENCY_HIGH,
    LOG_DB_CONN,
    LOG_INJECTION_SUSPECT,
    LOG_SENSITIVE_DATA,
    QUEUE_GROWING,
    WORKERS_DOWN,
    LogLine,
    Sample,
)

LOG_PATTERNS = {
    LOG_DB_CONN: re.compile(r"too many connections|QueuePool limit|connection pool exhausted", re.IGNORECASE),
    LOG_SENSITIVE_DATA: re.compile(
        r"(export|dump|exfiltrat)\w*\W.*\b(users|customers|personal data|pii)\b", re.IGNORECASE),
    LOG_INJECTION_SUSPECT: re.compile(
        r"ignore (all )?(previous|prior) instructions|disregard .{0,30}instructions|"
        r"you are now|system prompt|игнорируй (все )?(предыдущие )?инструкц", re.IGNORECASE),
}


def queue_slope(samples: list[Sample]) -> float:
    """Наклон длины очереди (задач/с): коэффициент линейной регрессии по отсчётам."""
    if len(samples) < 2:
        return 0.0
    n = len(samples)
    t0 = samples[0].t
    xs = [s.t - t0 for s in samples]
    ys = [s.queue_len for s in samples]
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0.0


class SignalExtractor:
    def __init__(self, cfg: Settings | None = None) -> None:
        self.cfg = cfg or Settings()

    def extract(self, samples: list[Sample], logs: list[LogLine]) -> frozenset:
        cfg = self.cfg
        out: set[str] = set()
        if samples:
            last = samples[-1]
            window = samples[-cfg.slope_window:]
            growing = len(window) >= cfg.slope_window and queue_slope(window) > cfg.queue_slope_thr
            if last.workers_alive == 0:
                out.add(WORKERS_DOWN)
            if growing:
                out.add(QUEUE_GROWING)
            if last.p95_ms > cfg.latency_thr_ms:
                out.add(LATENCY_HIGH)
            if last.error_rate > cfg.error_rate_thr:
                out.add(ERROR_RATE_HIGH)
            if (last.workers_alive > 0 and last.queue_len > 0
                    and last.processed_rate < cfg.stalled_ratio * last.arrival_rate):
                out.add(CONSUMER_STALLED)
        for signal, pattern in LOG_PATTERNS.items():
            if any(pattern.search(line.text) for line in logs):
                out.add(signal)
        return frozenset(out)
