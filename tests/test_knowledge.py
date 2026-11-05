"""База знаний и поиск: целостность БЗ, нормализация терминов, гибридный поиск, деградация."""
from dataclasses import replace

import pytest

from sentinel.domain import (
    CONSUMER_STALLED,
    ERROR_RATE_HIGH,
    LATENCY_HIGH,
    LOG_DB_CONN,
    LOG_SENSITIVE_DATA,
    QUEUE_GROWING,
    WORKERS_DOWN,
)
from sentinel.knowledge import (
    EmbeddingError,
    HybridRetriever,
    KnowledgeBaseError,
    ensure_valid,
    problems,
)
from sentinel.knowledge.bm25 import BM25, tokenize
from sentinel.knowledge.criteria import holds, is_valid
from sentinel.knowledge.runbook import parse_runbook
from sentinel.knowledge.symptoms import SYMPTOMS
from sentinel.system import build_system


def q(signals, extra=""):
    return " ".join(sorted(signals) + [SYMPTOMS[s] for s in sorted(signals) if s in SYMPTOMS] + [extra])


def test_knowledge_base_is_consistent(runbooks, registry):
    assert len(runbooks) >= 20
    assert len({r.id for r in runbooks}) == len(runbooks)
    assert problems(runbooks, registry) == []


@pytest.mark.parametrize("change, message", [
    ({"signals_required": ("NO_SUCH_SIGNAL",)}, "неизвестный сигнал"),
    ({"actions": ("drop_database",)}, "отсутствует в реестре"),
    ({"success_criteria": ("cpu < 50",)}, "нераспознанный критерий"),
    ({"signals_excluded": ("WORKERS_DOWN",)}, "одновременно обязателен"),
    ({"id": "RB-1"}, "шаблону"),
])
def test_validator_rejects_inconsistent_runbook(runbooks, registry, change, message):
    bad = replace(runbooks[0], **change)
    with pytest.raises(KnowledgeBaseError, match=message):
        ensure_valid([bad, *runbooks[1:]], registry)


def test_duplicate_id_is_rejected(runbooks, registry):
    assert any("повторяющийся" in p for p in problems([runbooks[0], runbooks[0]], registry))


def test_system_refuses_to_start_with_broken_knowledge_base(runbooks):
    with pytest.raises(KnowledgeBaseError):
        build_system(runbooks=[replace(runbooks[0], actions=("rm_rf",))])


def test_runbook_without_front_matter_is_rejected():
    with pytest.raises(ValueError):
        parse_runbook("просто текст без заголовка")


def test_snowball_normalizes_word_forms_but_keeps_identifiers():
    assert tokenize("воркеры") == tokenize("воркеров")
    assert tokenize("очередь растёт") == tokenize("очереди растет")
    assert tokenize("WORKERS_DOWN restart_workers 4711") == ["workers_down", "restart_workers", "4711"]
    assert tokenize("connections") == tokenize("connection")


def test_bm25_prefers_matching_document():
    bm = BM25(["воркеры остановлены очередь растёт", "доля ошибок выросла база данных"])
    assert bm.score("очереди воркеров", 0) > bm.score("очереди воркеров", 1)


def test_success_criteria_grammar():
    assert is_valid("not WORKERS_DOWN") and is_valid("queue_len < 50") and not is_valid("cpu < 1")
    assert holds("not WORKERS_DOWN", frozenset(), [])
    with pytest.raises(ValueError):
        holds("cpu < 1", frozenset(), [])


def test_hybrid_finds_expected_runbook(retriever):
    cases = {
        (frozenset({WORKERS_DOWN, QUEUE_GROWING}), "Worker exited prematurely signal 9 (SIGKILL)"): "RB-001",
        (frozenset({QUEUE_GROWING, LATENCY_HIGH}), "took 9.1s (slow downstream response)"): "RB-002",
        (frozenset({ERROR_RATE_HIGH, LOG_DB_CONN}), "sqlalchemy QueuePool limit reached"): "RB-003",
        (frozenset({CONSUMER_STALLED, QUEUE_GROWING}), "message redelivered 50 times"): "RB-004",
        (frozenset({LOG_SENSITIVE_DATA}), "export job dumped users personal data"): "RB-005",
    }
    for (signals, logs), expected in cases.items():
        found = retriever.search(q(signals, logs), signals, "demo-api")
        assert found and found[0].runbook.id == expected, (signals, [r.runbook.id for r in found])
        assert all(0 < r.s_ret <= 1.0 for r in found) and len(found) <= 3


def test_prefilter_respects_service_and_signals(retriever):
    assert retriever.search("что-то странное", frozenset({"UNKNOWN_SIGNAL"}), "demo-api") == []
    assert retriever.search(q({WORKERS_DOWN}), frozenset({WORKERS_DOWN}), "other-service") == []
    found = retriever.search(q({WORKERS_DOWN, QUEUE_GROWING}), frozenset({WORKERS_DOWN, QUEUE_GROWING}),
                             "demo-api")
    assert {r.runbook.service for r in found} == {"demo-api"}


class BrokenEmbedder:
    name = "broken"

    def __init__(self):
        self.calls = 0

    def encode(self, texts):
        self.calls += 1
        if self.calls > 1:                     # индексация прошла, сервис упал во время работы
            raise EmbeddingError("connection refused")
        import numpy as np
        return np.ones((len(texts), 4), dtype=np.float32) / 2


def test_retrieval_degrades_to_bm25_when_embeddings_unavailable(runbooks, cfg):
    r = HybridRetriever(runbooks, embedder=BrokenEmbedder(), cfg=cfg)
    signals = frozenset({WORKERS_DOWN, QUEUE_GROWING})
    found = r.search(q(signals, "signal 9 (SIGKILL)"), signals, "demo-api")
    assert r.degraded and found and all(x.dense_rank is None for x in found)
