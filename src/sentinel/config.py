"""Параметры системы. Значения соответствуют разделу 2 пояснительной записки."""
from __future__ import annotations

from dataclasses import dataclass, field

from sentinel.domain import Risk


@dataclass(frozen=True)
class Settings:
    # детектор
    period_s: float = 5.0            # период измерений Δ
    debounce_k: int = 3              # условие должно держаться k измерений подряд
    slope_window: int = 6            # отсчётов для наклона очереди (30 с)
    queue_slope_thr: float = 1.0     # задач/с
    latency_thr_ms: float = 5000.0
    error_rate_thr: float = 0.05
    stalled_ratio: float = 0.05
    log_window_s: float = 30.0
    anomaly_quantile: float = 0.99   # доля нормальных точек ниже порога θ_a
    # поиск
    top_k: int = 3
    rrf_k: int = 60
    s_min: float = 0.15
    # верификация и уверенность
    w_llm: float = 0.3
    w_ret: float = 0.2
    w_sig: float = 0.5
    m_min: float = 0.75
    # политика
    tau_auto: dict = field(default_factory=lambda: {Risk.LOW: 0.70, Risk.MEDIUM: 0.85})
    tau_esc: float = 0.40
    max_attempts: int = 3
    cooldown_s: float = 30.0
    # цикл обработки
    verify_wait_s: float = 30.0
    verify_consecutive: int = 2
    max_hypotheses: int = 3
    llm_retries: int = 2
    log_line_limit: int = 200
