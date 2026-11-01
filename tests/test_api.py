import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from sentinel.api import create_app


def test_hitl_flow_over_rest():
    client = TestClient(create_app())
    assert client.get("/health").json()["status"] == "ok"
    client.post("/demo/tick", params={"n": 12})
    client.post("/demo/faults/poison_message")
    opened = client.post("/demo/tick", params={"n": 40}).json()["incidents"]
    assert opened and opened[0]["state"] == "AWAITING_APPROVAL"
    iid = opened[0]["id"]
    assert opened[0]["pending"]["action"] == "purge_queue"
    assert client.post(f"/incidents/{iid}/approve").json()["state"] == "RESOLVED"
    assert client.post(f"/incidents/{iid}/approve").status_code == 409
    assert "Целостность журнала: подтверждена" in client.get(f"/incidents/{iid}").json()["report"]


def test_unknown_incident_and_fault():
    client = TestClient(create_app())
    assert client.get("/incidents/INC-9999").status_code == 404
    assert client.post("/demo/faults/nope").status_code == 404
