import sqlite3

from sentinel.service import ServiceSimulator
from sentinel.tools import Executor


def test_hash_chain_detects_tampering(store):
    for i in range(3):
        store.append("INC-1", "system", "step", {"i": i}, ts=float(i))
    assert store.verify_chain("INC-1")
    store.db.execute("UPDATE audit_events SET payload='{\"i\": 99}' WHERE seq=2")
    assert not store.verify_chain("INC-1")


def test_chains_are_independent_per_incident(store):
    store.append("A", "system", "x", {}, 0.0)
    store.append("B", "system", "x", {}, 0.0)
    assert store.verify_chain("A") and store.verify_chain("B")
    assert [e.seq for e in store.events("A")] == [1]


def test_duplicate_delivery_does_not_repeat_action(registry, store):
    sim = ServiceSimulator()
    ex = Executor(sim, registry, store)
    first = ex.execute("INC-1", "restart_workers", {}, attempt=1)
    again = ex.execute("INC-1", "restart_workers", {}, attempt=1)
    other_attempt = ex.execute("INC-1", "restart_workers", {}, attempt=2)
    assert (first.status, again.status, other_attempt.status) == ("ok", "duplicate", "ok")
    assert [a for a, _ in sim.executed] == ["restart_workers", "restart_workers"]


def test_executor_refuses_actions_outside_registry(registry, store):
    sim = ServiceSimulator()
    res = Executor(sim, registry, store).execute("INC-1", "drop_database", {}, 1)
    assert res.status == "failed" and sim.executed == []


def test_unique_idempotency_key_in_db(store):
    assert store.reserve_execution("k", "INC-1", "a", 0.0)
    assert not store.reserve_execution("k", "INC-1", "a", 0.0)
    assert isinstance(store.db, sqlite3.Connection)
