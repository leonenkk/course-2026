"""Сквозные сценарии С1--С6 (таблица 2.2 записки) и режимы сравнения."""
import pytest

from sentinel.audit import build_report
from sentinel.domain import State
from sentinel.scenarios import SCENARIOS, run_scenario


@pytest.mark.parametrize("key", list(SCENARIOS))
@pytest.mark.parametrize("seed", [1, 7])
def test_scenario(key, seed):
    res = run_scenario(SCENARIOS[key], seed=seed)
    assert res.ok, build_report(res.system.store, res.run.incident.id) if res.run else "no incident"
    if res.run:
        assert res.system.store.verify_chain(res.run.incident.id)


def test_sensitive_data_never_triggers_remediation():
    res = run_scenario(SCENARIOS["c5"])
    system, run = res.system, res.run
    assert run.state is State.ESCALATED
    assert [a for a, _ in system.sim.executed] == ["create_ticket", "notify_oncall"]


def test_injected_command_is_blocked_by_verifier():
    res = run_scenario(SCENARIOS["c6"])
    system, run = res.system, res.run
    verified = [e for e in system.store.events(run.incident.id) if e.type == "verified"]
    assert any(e.payload["action"] == "purge_queue" and "V3" in e.payload["failed"] for e in verified)
    assert "purge_queue" not in [a for a, _ in system.sim.executed]


def test_high_risk_action_waits_for_human_when_no_approver():
    from sentinel.system import build_system

    system = build_system()
    for _ in range(12):
        system.tick()
    system.sim.inject("poison_message")
    run = system.run_until_incident()
    assert run.state is State.AWAITING_APPROVAL and system.sim.executed == []
    done = system.orchestrator.decide_approval(run.incident.id, approve=True)
    assert done.state is State.RESOLVED and ("purge_queue" in [a for a, _ in system.sim.executed])


def test_rules_only_mode_runs_without_model():
    res = run_scenario(SCENARIOS["c1"], mode="rules_only")
    system, run = res.system, res.run
    assert run.state in (State.RESOLVED, State.AWAITING_APPROVAL, State.ESCALATED)
    assert system.orchestrator.llm.calls == 0
