import pytest

from sentinel.agent import IllegalTransition, StateMachine
from sentinel.domain import State


def test_happy_path():
    fsm = StateMachine()
    for s in (State.DIAGNOSING, State.PLANNED, State.ACTING, State.VERIFYING, State.RESOLVED):
        fsm.to(s)
    assert fsm.final


def test_next_hypothesis_loop():
    fsm = StateMachine()
    for s in (State.DIAGNOSING, State.PLANNED, State.ACTING, State.VERIFYING, State.PLANNED):
        fsm.to(s)
    assert not fsm.final


@pytest.mark.parametrize("src,dst", [
    (State.NEW, State.ACTING), (State.DIAGNOSING, State.ACTING), (State.PLANNED, State.VERIFYING),
    (State.RESOLVED, State.ESCALATED), (State.ESCALATED, State.NEW)])
def test_illegal_transitions_rejected(src, dst):
    fsm = StateMachine()
    fsm.state = src
    with pytest.raises(IllegalTransition):
        fsm.to(dst)


def test_any_active_state_can_escalate():
    for s in (State.NEW, State.DIAGNOSING, State.PLANNED, State.AWAITING_APPROVAL, State.ACTING,
              State.VERIFYING):
        fsm = StateMachine()
        fsm.state = s
        fsm.to(State.ESCALATED)
