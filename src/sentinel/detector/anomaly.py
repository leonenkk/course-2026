"""Статистический детектор аномалий: Isolation Forest, обученный на нормальной работе."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest

from sentinel.detector.signals import queue_slope
from sentinel.domain import Sample


def features(window: list[Sample]) -> list[float]:
    """Вектор x = (q, dq/dt, n_alive, e, p95, mu) для последнего измерения окна."""
    s = window[-1]
    return [s.queue_len, queue_slope(window), float(s.workers_alive), s.error_rate, s.p95_ms,
            s.processed_rate]


class AnomalyModel:
    def __init__(self, n_trees: int = 100, max_samples: int = 256, quantile: float = 0.99,
                 seed: int = 0) -> None:
        self.model = IsolationForest(n_estimators=n_trees, max_samples=max_samples,
                                     random_state=seed)
        self.quantile = quantile
        self.threshold = 1.0

    def fit(self, samples: list[Sample], window: int = 6) -> AnomalyModel:
        rows = [features(samples[i - window:i]) for i in range(window, len(samples) + 1)]
        x = np.asarray(rows)
        self.model.fit(x)
        scores = -self.model.score_samples(x)        # s(x, n) из статьи Лю и др.
        self.threshold = float(np.quantile(scores, self.quantile))
        return self

    def score(self, window: list[Sample]) -> float:
        return float(-self.model.score_samples(np.asarray([features(window)]))[0])

    def is_anomaly(self, window: list[Sample]) -> bool:
        return self.score(window) > self.threshold
