"""Режимы сравнения, бюджет обработки и отказы модели (отрицательные случаи)."""
from dataclasses import replace

import pytest

from sentinel.agent import Orchestrator
from sentinel.config import Settings
from sentinel.domain import State
from sentinel.llm import FailingLLM, StubLLM
from sentinel.scenarios import SCENARIOS, run_scenario
from sentinel.system import build_system


def test_llm_only_is_refused_outside_simulator():
    system = build_system()

    class RealService:                          # нет флага sandbox
        name = "prod"

    o = system.orchestrator
    with pytest.raises(ValueError, match="simulator"):
        Orchestrator(RealService(), o.retriever, o.llm, o.policy, o.executor, o.verifier, o.store,
                     mode="llm_only")


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        build_system(mode="magic")


def test_llm_only_executes_injected_command_without_policy():
    """Без символьного слоя «послушная» модель выполняет команду из лога --- то, что hybrid блокирует."""
    res = run_scenario(SCENARIOS["c6"], mode="llm_only")
    assert "purge_queue" in res.executed and not res.ok
    hybrid = run_scenario(SCENARIOS["c6"], mode="hybrid")
    assert "purge_queue" not in hybrid.executed and hybrid.ok


def test_llm_only_ignores_sensitive_data_policy():
    res = run_scenario(SCENARIOS["c5"], mode="llm_only")
    assert any(a in res.executed for a in ("restart_workers", "scale_workers", "purge_queue"))


def test_rules_only_never_calls_model():
    res = run_scenario(SCENARIOS["c1"], mode="rules_only")
    assert res.ok and res.system.orchestrator.llm.calls == 0


@pytest.mark.parametrize("fault, reason", [("unavailable", "llm_unavailable"),
                                           ("garbage", "llm_invalid_response")])
def test_model_failures_escalate_without_remediation(fault, reason):
    res = run_scenario(replace(SCENARIOS["c1"], llm_fault=fault, expect_state=State.ESCALATED))
    assert res.run.reason == reason and res.executed == ["create_ticket", "notify_oncall"]
    assert isinstance(res.system.orchestrator.llm, FailingLLM)


def test_processing_budget_escalates():
    system = build_system(llm=StubLLM(), cfg=Settings(max_active_s=0.0))
    for _ in range(12):
        system.tick()
    system.sim.inject("workers_crash")
    run = system.run_until_incident()
    assert run.state is State.ESCALATED and run.reason == "budget_exceeded"
    assert system.orchestrator.llm.calls == 0


def test_run_records_stage_timings_and_mttr():
    res = run_scenario(SCENARIOS["c1"])
    assert {"context", "retrieval", "llm", "verification", "policy", "execution"} <= set(res.run.timings)
    assert res.run.closed_at > res.inject_t and res.run.approvals == 0


def test_transient_fault_disappears_by_itself():
    system = build_system()
    system.sim.inject("latency_blip", duration_s=10)
    system.sim.advance(20)
    assert "latency_blip" not in system.sim.faults
