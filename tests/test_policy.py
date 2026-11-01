import pytest

from sentinel.domain import (
    LOG_INJECTION_SUSPECT,
    LOG_SENSITIVE_DATA,
    WORKERS_DOWN,
    ActionProposal,
    Verdict,
)
from sentinel.policy import PolicyEngine


@pytest.fixture
def policy(registry, cfg):
    return PolicyEngine(registry, cfg)


def ev(policy, action="restart_workers", params=None, c=0.9, signals=frozenset(), attempts=0, since=None):
    return policy.evaluate(ActionProposal(action, params or {}), c, frozenset(signals), attempts, since)


def test_low_risk_high_confidence_is_auto(policy):
    d = ev(policy)
    assert d.verdict is Verdict.AUTO_EXECUTE and d.fired == ()


def test_p1_unknown_action_denied(policy):
    assert ev(policy, "rm_rf").verdict is Verdict.DENY


def test_p1_param_limit_denied(policy):
    d = ev(policy, "scale_workers", {"delta": 50})
    assert d.verdict is Verdict.DENY and "P1" in d.fired


def test_p2_sensitive_data_escalates(policy):
    assert ev(policy, signals={LOG_SENSITIVE_DATA}).verdict is Verdict.ESCALATE


def test_p3_injection_requires_approval(policy):
    d = ev(policy, signals={LOG_INJECTION_SUSPECT, WORKERS_DOWN})
    assert d.verdict is Verdict.REQUIRE_APPROVAL and d.fired == ("P3",)


def test_p4_high_risk_never_auto(policy):
    d = ev(policy, "purge_queue", {"queue": "default"}, c=1.0)
    assert d.verdict is Verdict.REQUIRE_APPROVAL and "P4" in d.fired


def test_p5_low_confidence_escalates(policy):
    assert ev(policy, c=0.3).verdict is Verdict.ESCALATE


def test_p6_medium_risk_needs_higher_confidence(policy):
    assert ev(policy, "scale_workers", {"delta": 2}, c=0.8).verdict is Verdict.REQUIRE_APPROVAL
    assert ev(policy, "scale_workers", {"delta": 2}, c=0.9).verdict is Verdict.AUTO_EXECUTE


def test_p7_attempt_limit_and_cooldown(policy):
    assert ev(policy, attempts=3).verdict is Verdict.ESCALATE
    assert ev(policy, since=5.0).verdict is Verdict.ESCALATE


def test_most_restrictive_verdict_wins(policy):
    d = ev(policy, "purge_queue", {"queue": "default"}, c=0.2, signals={LOG_SENSITIVE_DATA})
    assert d.verdict is Verdict.ESCALATE and {"P2", "P4", "P5"} <= set(d.fired)
    assert ev(policy, "rm_rf", c=0.1, signals={LOG_SENSITIVE_DATA}).verdict is Verdict.DENY
