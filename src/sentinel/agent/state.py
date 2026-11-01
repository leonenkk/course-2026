"""Автомат состояний инцидента (рисунок 2.4): допустимы только переходы из таблицы."""
from __future__ import annotations

from sentinel.domain import FINAL_STATES, State

TRANSITIONS: dict[State, frozenset] = {
    State.NEW: frozenset({State.DIAGNOSING, State.ESCALATED}),
    State.DIAGNOSING: frozenset({State.PLANNED, State.ESCALATED}),
    State.PLANNED: frozenset({State.ACTING, State.AWAITING_APPROVAL, State.ESCALATED}),
    State.AWAITING_APPROVAL: frozenset({State.ACTING, State.ESCALATED}),
    State.ACTING: frozenset({State.VERIFYING, State.ESCALATED}),
    State.VERIFYING: frozenset({State.RESOLVED, State.PLANNED, State.ESCALATED}),
    State.RESOLVED: frozenset(),
    State.ESCALATED: frozenset(),
}


class IllegalTransition(RuntimeError):
    pass


class StateMachine:
    def __init__(self) -> None:
        self.state = State.NEW
        self.history: list[State] = [State.NEW]

    @property
    def final(self) -> bool:
        return self.state in FINAL_STATES

    def to(self, new: State) -> None:
        if new not in TRANSITIONS[self.state]:
            raise IllegalTransition(f"{self.state.value} -> {new.value}")
        self.state = new
        self.history.append(new)
