from sentinel.domain import (
    CONSUMER_STALLED,
    ERROR_RATE_HIGH,
    LATENCY_HIGH,
    LOG_DB_CONN,
    LOG_SENSITIVE_DATA,
    QUEUE_GROWING,
    WORKERS_DOWN,
)
from sentinel.knowledge.bm25 import BM25, tokenize
from sentinel.knowledge.symptoms import SYMPTOMS


def q(signals):
    return " ".join(sorted(signals) + [SYMPTOMS[s] for s in sorted(signals) if s in SYMPTOMS])


def test_runbooks_loaded_with_consistent_ids(runbooks):
    assert [r.id for r in runbooks] == ["RB-001", "RB-002", "RB-003", "RB-004", "RB-005"]
    assert all(r.actions for r in runbooks)


def test_bm25_prefers_matching_document():
    bm = BM25(["воркеры остановлены очередь растёт", "доля ошибок выросла база данных"])
    assert bm.score("очередь воркеры", 0) > bm.score("очередь воркеры", 1)
    assert tokenize("WORKERS_DOWN") == ["workers_down"]


def test_hybrid_finds_expected_runbook(retriever):
    cases = {
        frozenset({WORKERS_DOWN, QUEUE_GROWING}): "RB-001",
        frozenset({QUEUE_GROWING, LATENCY_HIGH}): "RB-002",
        frozenset({ERROR_RATE_HIGH, LOG_DB_CONN}): "RB-003",
        frozenset({CONSUMER_STALLED, QUEUE_GROWING}): "RB-004",
        frozenset({LOG_SENSITIVE_DATA}): "RB-005",
    }
    for signals, expected in cases.items():
        found = retriever.search(q(signals), signals, "demo-api")
        assert found and found[0].runbook.id == expected, (signals, found)
        assert all(0 < r.s_ret <= 1.0 for r in found) and len(found) <= 3


def test_empty_result_without_matching_signals_or_service(retriever):
    assert retriever.search("что-то странное", frozenset({"UNKNOWN_SIGNAL"}), "demo-api") == []
    assert retriever.search(q({WORKERS_DOWN}), frozenset({WORKERS_DOWN}), "other-service") == []
