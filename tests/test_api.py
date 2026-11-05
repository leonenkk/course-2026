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


def test_approver_label_cannot_spoof_audit_actor():
    client = make()
    client.post("/demo/tick", params={"n": 12})
    client.post("/demo/faults/poison_message")
    iid = client.post("/demo/tick", params={"n": 40}).json()["incidents"][0]["id"]
    for bad in ("auto", "oncall", "Admin", "a b", "x" * 65):
        assert client.post(f"/incidents/{iid}/approve", headers={"X-Approver": bad}).status_code == 400
    assert client.get(f"/incidents/{iid}").json()["state"] == "AWAITING_APPROVAL"
    assert client.post(f"/incidents/{iid}/approve", headers={"X-Approver": "ivan.petrov"}).status_code == 200
    ev = next(e for e in client.get(f"/incidents/{iid}").json()["audit"] if e["type"] == "approval")
    assert ev["actor"] == "human:oncall" and ev["payload"]["label"] == "ivan.petrov"


def test_panel_is_static_and_protected_by_csp():
    client = TestClient(create_app(token="secret", dev=False))          # без токена
    page = client.get("/")
    assert page.status_code == 200 and "Sentinel" in page.text
    assert "default-src 'none'" in page.headers["content-security-policy"]
    assert "secret" not in page.text                                      # токен не встраивается в страницу
    assert "innerHTML" not in page.text                                   # недоверенный текст --- только textContent
    assert client.get("/config").status_code == 401


def test_config_hides_faults_outside_dev_mode():
    cfg = make(dev=False).get("/config").json()
    assert cfg["dev"] is False and cfg["faults"] == [] and cfg["runbooks"] >= 20


def test_config_exposes_confidence_formula_and_thresholds():
    cfg = make().get("/config").json()
    assert cfg["weights"] == {"llm": 0.3, "ret": 0.2, "sig": 0.5}
    assert cfg["thresholds"] == {"escalate": 0.4, "auto_low": 0.7, "auto_medium": 0.85}


def test_card_explains_diagnosis():
    client = make()
    client.post("/demo/tick", params={"n": 12})
    client.post("/demo/faults/workers_crash")
    inc = client.post("/demo/tick", params={"n": 40}).json()["incidents"][0]
    d = client.get(f"/incidents/{inc['id']}").json()
    assert d["state"] == "RESOLVED" and d["chain_ok"] is True
    diag = d["diagnosis"]
    assert diag["action"] == "restart_workers" and {"c_llm", "s_ret", "m_sig", "explanation"} <= set(diag)
    assert abs(diag["confidence"] - (0.3 * diag["c_llm"] + 0.2 * diag["s_ret"] + 0.5 * diag["m_sig"])) < 0.01
    assert "llm" in d["timings_ms"] and d["retrieved"]
