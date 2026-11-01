import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from sentinel.api import create_app

AUTH = {"Authorization": "Bearer secret"}


def make(dev=True):
    return TestClient(create_app(token="secret", dev=dev), headers=AUTH)


def test_hitl_flow_over_rest():
    client = make()
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
    client = make()
    assert client.get("/incidents/INC-9999").status_code == 404
    assert client.post("/demo/faults/nope").status_code == 404


def test_all_routes_except_health_require_token():
    anon = TestClient(create_app(token="secret", dev=True))
    assert anon.get("/health").status_code == 200
    for method, url in (("get", "/incidents"), ("get", "/incidents/INC-0001"),
                        ("post", "/incidents/INC-0001/approve"), ("post", "/demo/tick"),
                        ("post", "/demo/faults/noise")):
        assert getattr(anon, method)(url).status_code == 401, url
        assert getattr(anon, method)(url, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_demo_routes_disabled_outside_dev_mode():
    client = make(dev=False)
    assert client.post("/demo/tick").status_code == 404
    assert client.post("/demo/faults/noise").status_code == 404
    assert client.get("/incidents").status_code == 200


def test_refuses_to_start_without_token(monkeypatch):
    monkeypatch.delenv("SENTINEL_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        create_app()
