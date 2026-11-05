"""Гибридный поиск: предфильтр, BM25 и векторный поиск, слияние RRF (формулы 2.2--2.3 записки).

``search`` --- рабочий путь (предфильтр по сервису и сигналам, top-k, порог ``s_min``).
``rank`` --- полное ранжирование кандидатов, используется также в экспериментах по качеству поиска.
Если сервис эмбеддингов недоступен во время запроса, поиск деградирует до BM25 и выставляет
флаг ``degraded`` (решение фиксируется в аудите), а не падает.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sentinel.config import Settings
from sentinel.knowledge.bm25 import BM25
from sentinel.knowledge.embedder import Embedder, EmbeddingError, HashingEmbedder
from sentinel.knowledge.runbook import Runbook


@dataclass(frozen=True)
class Retrieved:
    runbook: Runbook
    s_ret: float          # нормированная оценка RRF из (0; 1]
    bm25_rank: int | None
    dense_rank: int | None


class HybridRetriever:
    def __init__(self, runbooks: list[Runbook], embedder: Embedder | None = None,
                 cfg: Settings | None = None, dense_min: float = 0.1, dense_top: int = 5,
                 stem: str = "snowball") -> None:
        self.cfg = cfg or Settings()
        self.runbooks = runbooks
        self.embedder = embedder or HashingEmbedder()
        self.dense_min, self.dense_top = dense_min, dense_top
        self.bm25 = BM25([r.text for r in runbooks], stem=stem)
        # эмбеддинги документов считаются один раз при индексации
        self.vectors = (self.embedder.encode([r.text for r in runbooks]) if runbooks
                        else np.zeros((0, 1), dtype=np.float32))
        self.degraded = False

    def candidates(self, observed: frozenset, service: str) -> list[int]:
        """Символьный предфильтр: тот же сервис и хотя бы один общий обязательный сигнал."""
        return [i for i, r in enumerate(self.runbooks)
                if r.service == service and observed & set(r.signals_required)]

    def rank(self, query: str, cand: list[int], use_bm25: bool = True,
             use_dense: bool = True) -> list[Retrieved]:
        if not cand:
            return []
        bm_rank: dict[int, int] = {}
        if use_bm25:
            bm = sorted(zip(self.bm25.scores(query, cand), cand), key=lambda p: (-p[0], p[1]))
            bm_rank = {i: r for r, (s, i) in enumerate(bm, start=1) if s > 0}
        dn_rank: dict[int, int] = {}
        self.degraded = False
        if use_dense:
            try:
                qv = self.embedder.encode([query])[0]
                sims = self.vectors[cand] @ qv
                dn = sorted(zip(sims.tolist(), cand), key=lambda p: (-p[0], p[1]))
                dn_rank = {i: r for r, (s, i) in enumerate(dn[: self.dense_top], start=1)
                           if s >= self.dense_min}
            except EmbeddingError:
                self.degraded = True                       # остаётся только лексический поиск
        k = self.cfg.rrf_k
        best = 2.0 / (k + 1)
        scored = [Retrieved(self.runbooks[i],
                            sum(1.0 / (k + r[i]) for r in (bm_rank, dn_rank) if i in r) / best,
                            bm_rank.get(i), dn_rank.get(i))
                  for i in set(bm_rank) | set(dn_rank)]
        scored.sort(key=lambda r: (-r.s_ret, r.runbook.id))
        return scored

    def search(self, query: str, observed: frozenset, service: str) -> list[Retrieved]:
        scored = self.rank(query, self.candidates(observed, service))[: self.cfg.top_k]
        if not scored or scored[0].s_ret < self.cfg.s_min:
            return []                       # отсутствие знаний: модель не вызывается
        return scored
