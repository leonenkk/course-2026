"""Производительность компонентов и влияние объёма базы знаний на время поиска.

База искусственно увеличивается копиями реальных инструкций (новые идентификаторы и сервисы),
векторы --- случайные нормированные размерности 1024, как у BGE-M3: так измеряется стоимость самого
ранжирования, а время эмбеддинга запроса нейросетью приводится отдельно (оно от объёма базы не зависит).
"""
from __future__ import annotations

import time
from dataclasses import replace

import numpy as np

from sentinel.config import Settings
from sentinel.detector import AnomalyModel, Detector
from sentinel.eval import environment, percentile
from sentinel.knowledge import HybridRetriever, Runbook
from sentinel.service import ServiceSimulator


class RandomEmbedder:
    """Случайные нормированные векторы фиксированной размерности (только для замеров времени)."""

    name = "random-1024"

    def __init__(self, dim: int = 1024, seed: int = 0) -> None:
        self.dim, self.rng = dim, np.random.default_rng(seed)

    def encode(self, texts: list[str]) -> np.ndarray:
        x = self.rng.standard_normal((len(texts), self.dim)).astype(np.float32)
        return x / np.linalg.norm(x, axis=1, keepdims=True)


def _scaled(runbooks: list[Runbook], n: int) -> list[Runbook]:
    out = []
    for i in range(n):
        rb = runbooks[i % len(runbooks)]
        out.append(replace(rb, id=f"RB-{i:06d}", service=f"{rb.service}-{i // len(runbooks)}"))
    return out


def _timeit(fn, repeat: int) -> list[float]:
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return times


def kb_scaling(runbooks: list[Runbook], sizes: tuple = (24, 100, 500, 1000, 5000, 10000),
               query: str = "WORKERS_DOWN QUEUE_GROWING воркеры не отвечают Worker exited SIGKILL",
               repeat: int = 30) -> list[dict]:
    rows = []
    for n in sizes:
        kb = _scaled(runbooks, n)
        t0 = time.perf_counter()
        r = HybridRetriever(kb, RandomEmbedder())
        build_ms = (time.perf_counter() - t0) * 1000
        everything = list(range(n))
        full = _timeit(lambda r=r, c=everything: r.rank(query, c), repeat)
        filtered = _timeit(lambda r=r: r.rank(query, r.candidates(frozenset({"WORKERS_DOWN"}), "demo-api-0")),
                           repeat)
        rows.append({"runbooks": n, "index_build_ms": build_ms,
                     "rank_all_ms_p50": percentile(full, 50), "rank_all_ms_p95": percentile(full, 95),
                     "prefiltered_ms_p50": percentile(filtered, 50),
                     "vectors_kb": r.vectors.nbytes / 1024})
    return rows


def detector_cost(steps: int = 500) -> dict:
    cfg = Settings()
    sim = ServiceSimulator(seed=1)
    sim.advance(cfg.period_s * 400)
    t0 = time.perf_counter()
    model = AnomalyModel(quantile=cfg.anomaly_quantile).fit(sim.samples(400))
    fit_ms = (time.perf_counter() - t0) * 1000
    det = Detector(sim.name, cfg, model)
    step_times, score_times = [], []
    for _ in range(steps):
        sim.advance(cfg.period_s)
        window, logs = sim.samples(cfg.slope_window), sim.logs(cfg.log_window_s)
        step_times += _timeit(lambda w=window, lg=logs: det.step(w, lg), 1)
        score_times += _timeit(lambda w=window: model.score(w), 1)
    return {"if_fit_ms": fit_ms, "if_trees": 100, "if_psi": 256,
            "detector_step_ms_p50": percentile(step_times, 50),
            "detector_step_ms_p95": percentile(step_times, 95),
            "if_score_ms_p50": percentile(score_times, 50)}


def query_embedding_cost(embedder, repeat: int = 20) -> dict:
    texts = ["WORKERS_DOWN QUEUE_GROWING воркеры не отвечают ERROR: Worker exited prematurely signal #"]
    embedder.encode(texts)                                   # прогрев (загрузка модели)
    t = _timeit(lambda: embedder.encode(texts), repeat)
    return {"embedder": embedder.name, "query_ms_p50": percentile(t, 50), "query_ms_p95": percentile(t, 95)}


def evaluate(runbooks: list[Runbook], embedder=None) -> dict:
    out = {"environment": environment(), "kb_scaling": kb_scaling(runbooks), "detector": detector_cost()}
    if embedder is not None:
        out["query_embedding"] = query_embedding_cost(embedder)
    return out
