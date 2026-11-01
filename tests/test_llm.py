import json

import pytest

from sentinel.domain import State
from sentinel.llm import ResponseError, StubLLM, parse_response
from sentinel.system import build_system


def test_parse_valid_response():
    text = json.dumps({"insufficient_data": False, "hypotheses": [{
        "runbook_id": "RB-001", "cause": "c", "explanation": "e",
        "action": {"name": "restart_workers", "params": {}}, "confidence": 0.9}]})
    assert parse_response(text)[0].action.name == "restart_workers"


@pytest.mark.parametrize("bad", ["not json", "{}", '{"insufficient_data": false, "hypotheses": [{"runbook_id": 1}]}',
                                 json.dumps({"insufficient_data": False, "hypotheses": [{
                                     "runbook_id": "RB-001", "cause": "c", "explanation": "e",
                                     "action": {"name": "x", "params": {}}, "confidence": 7}]})])
def test_invalid_response_rejected(bad):
    with pytest.raises(ResponseError):
        parse_response(bad)


def test_insufficient_data_gives_no_hypotheses():
    assert parse_response('{"insufficient_data": true, "hypotheses": []}') == []


class FlakyLLM(StubLLM):
    """Первые два ответа не соответствуют схеме."""

    def complete(self, system, user, schema):
        if self.calls < 2:
            self.calls += 1
            return "garbage"
        return super().complete(system, user, schema)


def _crash(llm):
    system = build_system(llm=llm)
    for _ in range(12):
        system.tick()
    system.sim.inject("workers_crash")
    return system.run_until_incident()


def test_model_unavailable_escalates_without_actions():
    run = _crash(StubLLM(fail=True))
    assert run.state is State.ESCALATED and run.reason == "llm_unavailable"


def test_invalid_format_is_retried_then_recovers():
    llm = FlakyLLM()
    run = _crash(llm)
    assert llm.calls == 3 and run.state is State.RESOLVED


def test_persistent_garbage_escalates():
    class Garbage(StubLLM):
        def complete(self, system, user, schema):
            return "garbage"

    run = _crash(Garbage())
    assert run.state is State.ESCALATED and run.reason == "llm_invalid_response"
