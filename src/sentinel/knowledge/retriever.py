"""Гибридный поиск: предфильтр, BM25 и векторный поиск, слияние RRF (формулы 2.2--2.3 записки)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sentinel.config import Settings
from sentinel.knowledge.bm25 import BM25
from sentinel.knowledge.embedder import Embedder, HashingEmbedder
from sentinel.knowledge.runbook import Runbook


@dataclass(frozen=True)
class Retrieved:
    runbook: Runbook
    s_ret: float          # нормированная оценка RRF из (0; 1]
    bm25_rank: int | None
    dense_rank: int | None


class HybridRetriever:
    def __init__(self, runbooks: list[Runbook], embedder: Embedder | None = None,
                 cfg: Settings | None = None, dense_min: float = 0.1, dense_top: int = 5) -> None:
        self.cfg = cfg or Settings()
        self.runbooks = runbooks
        self.embedder = embedder or HashingEmbedder()
        self.dense_min, self.dense_top = dense_min, dense_top
        self.bm25 = BM25([r.text for r in runbooks])
        self.vectors = self.embedder.encode([r.text for r in runbooks])  # считаются один раз

    def search(self, query: str, observed: frozenset, service: str) -> list[Retrieved]:
        cand = [i for i, r in enumerate(self.runbooks)
                if r.service == service and observed & set(r.signals_required)]
        if not cand:
            return []
        bm = sorted(((self.bm25.score(query, i), i) for i in cand), reverse=True)
        bm_rank = {i: r for r, (s, i) in enumerate(bm, start=1) if s > 0}
        qv = self.embedder.encode([query])[0]
        dn = sorted(((float(np.dot(self.vectors[i], qv)), i) for i in cand), reverse=True)
        dn_rank = {i: r for r, (s, i) in enumerate(dn[: self.dense_top], start=1) if s >= self.dense_min}
        k = self.cfg.rrf_k
        best = 2.0 / (k + 1)
        scored = []
        for i in set(bm_rank) | set(dn_rank):
            rrf = sum(1.0 / (k + r[i]) for r in (bm_rank, dn_rank) if i in r)
            scored.append(Retrieved(self.runbooks[i], rrf / best, bm_rank.get(i), dn_rank.get(i)))
        scored.sort(key=lambda r: (-r.s_ret, r.runbook.id))
        scored = scored[: self.cfg.top_k]
        if not scored or scored[0].s_ret < self.cfg.s_min:
            return []                       # отсутствие знаний: модель не вызывается
        return scored
