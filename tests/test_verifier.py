import pytest

from sentinel.agent import Verifier, confidence
from sentinel.domain import (
    ERROR_RATE_HIGH,
    QUEUE_GROWING,
    WORKERS_DOWN,
    ActionProposal,
    Hypothesis,
)
from sentinel.knowledge.retriever import Retrieved


def hyp(rb="RB-001", action="restart_workers", params=None, c=0.9):
    return Hypothesis(rb, "cause", "expl", ActionProposal(action, params or {}), c)


@pytest.fixture
def found(runbooks):
    return [Retrieved(r, 1.0, 1, 1) for r in runbooks]


@pytest.fixture
def verifier(registry, cfg):
    return Verifier(registry, cfg)


OBS = frozenset({WORKERS_DOWN, QUEUE_GROWING})


def test_valid_hypothesis_passes_with_high_confidence(verifier, found):
    v = verifier.check(hyp(), found, OBS)
    assert v.ok and v.scored.m_sig == 1.0 and v.scored.confidence == pytest.approx(0.97)


def test_v2_runbook_not_retrieved(verifier, found):
    assert verifier.check(hyp("RB-999"), found, OBS).failed == ("V2",)
    assert verifier.check(hyp(), found[1:], OBS).failed == ("V2",)


def test_v3_action_not_in_runbook(verifier, found):
    assert "V3" in verifier.check(hyp(action="purge_queue", params={"queue": "default"}), found, OBS).failed


def test_v4_excluded_signal_contradicts_diagnosis(verifier, found):
    obs = frozenset({QUEUE_GROWING, "LATENCY_HIGH", ERROR_RATE_HIGH})
    assert "V4" in verifier.check(hyp("RB-002", "scale_workers", {"delta": 2}), found, obs).failed


def test_v4_partial_signal_match_rejected(verifier, found):
    assert "V4" in verifier.check(hyp(), found, frozenset({WORKERS_DOWN})).failed


def test_v5_bad_params(verifier, found):
    assert "V5" in verifier.check(hyp("RB-002", "scale_workers", {"delta": 99}), found,
                                  frozenset({QUEUE_GROWING, "LATENCY_HIGH"})).failed


def test_model_overconfidence_cannot_reach_auto_threshold(cfg):
    assert confidence(1.0, 1.0, 0.0, cfg) <= 0.5 < cfg.tau_auto[next(iter(cfg.tau_auto))]
