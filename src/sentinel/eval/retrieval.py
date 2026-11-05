"""Оценка качества поиска инструкций: Hit@1, Hit@3, MRR и время запроса.

Сравниваются лексический (BM25 с двумя способами нормализации), векторный (хэширующая заглушка и
нейросетевая модель) и гибридный поиск, каждый --- с символьным предфильтром и без него. Так видно
отдельно вклад каждого компонента и вклад символьного слоя в нейросетевой поиск.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from sentinel.eval import environment
from sentinel.knowledge import Embedder, HashingEmbedder, HybridRetriever, Runbook

DEFAULT_QUERIES = Path(__file__).resolve().parents[3] / "knowledge" / "eval" / "queries.yaml"


@dataclass(frozen=True)
class Query:
    id: str
    kind: str
    service: str
    signals: frozenset
    expected: str
    text: str


def load_queries(path: str | Path = DEFAULT_QUERIES) -> list[Query]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [Query(q["id"], q["kind"], q["service"], frozenset(q["signals"]), q["expected"], q["text"])
            for q in raw]


@dataclass(frozen=True)
class Config:
    name: str
    stem: str
    embedder: str        # ключ в словаре эмбеддеров
    bm25: bool
    dense: bool


def configs(neural: str | None) -> list[Config]:
    out = [Config("BM25 (усечение)", "truncate", "hashing", True, False),
           Config("BM25 (Snowball)", "snowball", "hashing", True, False),
           Config("Вектор (хэш-заглушка)", "snowball", "hashing", False, True),
           Config("Гибрид (Snowball + заглушка)", "snowball", "hashing", True, True)]
    if neural:
        out += [Config(f"Вектор ({neural})", "snowball", neural, False, True),
                Config(f"Гибрид (Snowball + {neural})", "snowball", neural, True, True)]
    return out


def _metrics(ranks: list[int | None], latencies: list[float]) -> dict:
    n = len(ranks)
    return {"n": n,
            "hit1": sum(r == 1 for r in ranks) / n,
            "hit3": sum(r is not None and r <= 3 for r in ranks) / n,
            "mrr": sum(1 / r for r in ranks if r) / n,
            "latency_ms": sum(latencies) / n}


def evaluate(runbooks: list[Runbook], queries: list[Query],
             embedders: dict[str, Embedder] | None = None) -> dict:
    embedders = embedders or {"hashing": HashingEmbedder()}
    neural = next((k for k in embedders if k != "hashing"), None)
    retrievers: dict[tuple, HybridRetriever] = {}
    rows = []
    for cfg in configs(neural):
        key = (cfg.stem, cfg.embedder)
        if key not in retrievers:
            # dense_top = все документы: в эксперименте нужно полное ранжирование
            retrievers[key] = HybridRetriever(runbooks, embedders[cfg.embedder], stem=cfg.stem,
                                              dense_top=len(runbooks), dense_min=-1.0)
        r = retrievers[key]
        for prefilter in (True, False):
            ranks, lat, per_kind = [], [], {}
            for q in queries:
                cand = r.candidates(q.signals, q.service) if prefilter else list(range(len(runbooks)))
                t0 = time.perf_counter()
                ranked = r.rank(q.text, cand, use_bm25=cfg.bm25, use_dense=cfg.dense)
                lat.append((time.perf_counter() - t0) * 1000)
                pos = next((i for i, x in enumerate(ranked, start=1) if x.runbook.id == q.expected), None)
                ranks.append(pos)
                per_kind.setdefault(q.kind, []).append(pos)
            rows.append({"config": cfg.name, "prefilter": prefilter, **_metrics(ranks, lat),
                         "by_kind": {k: _metrics(v, [0.0] * len(v)) for k, v in sorted(per_kind.items())}})
    return {"environment": environment(), "runbooks": len(runbooks), "queries": len(queries),
            "embedders": {k: e.name for k, e in embedders.items()}, "rows": rows}
