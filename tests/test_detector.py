from sentinel.detector import AnomalyModel, Detector, SignalExtractor, queue_slope
from sentinel.domain import CONSUMER_STALLED, LOG_INJECTION_SUSPECT, QUEUE_GROWING, WORKERS_DOWN
from sentinel.service import ServiceSimulator
from sentinel.system import build_system


def drive(sim, detector, cfg, ticks):
    incidents = []
    for _ in range(ticks):
        sim.advance(cfg.period_s)
        inc = detector.step(sim.samples(cfg.slope_window), sim.logs(cfg.log_window_s))
        if inc:
            incidents.append(inc)
    return incidents


def test_normal_operation_produces_no_signals_or_incidents(cfg):
    sim = ServiceSimulator()
    sim.advance(60)
    det = Detector(sim.name, cfg)
    assert drive(sim, det, cfg, 100) == []


def test_workers_crash_detected_after_debounce(cfg):
    sim = ServiceSimulator()
    sim.advance(60)
    det = Detector(sim.name, cfg)
    sim.inject("workers_crash")
    incidents = drive(sim, det, cfg, 20)
    assert len(incidents) == 1                       # дубликат с той же подписью не создаётся
    assert incidents[0].rule == "D1" and {WORKERS_DOWN, QUEUE_GROWING} <= incidents[0].signals


def test_noise_does_not_raise_incident(cfg):
    sim = ServiceSimulator()
    sim.advance(60)
    det = Detector(sim.name, cfg)
    sim.inject("noise")
    assert drive(sim, det, cfg, 80) == []


def test_stalled_consumer_signal(cfg):
    sim = ServiceSimulator()
    sim.advance(60)
    sim.inject("poison_message")
    sim.advance(60)
    sig = SignalExtractor(cfg).extract(sim.samples(6), sim.logs(30))
    assert CONSUMER_STALLED in sig and WORKERS_DOWN not in sig


def test_injection_text_is_flagged(cfg):
    sim = ServiceSimulator()
    sim.advance(30)
    sim.inject("workers_crash", injection=True)
    sim.advance(30)
    assert LOG_INJECTION_SUSPECT in SignalExtractor(cfg).extract(sim.samples(6), sim.logs(30))


def test_queue_slope_linear():
    sim = ServiceSimulator()
    sim.inject("workers_crash")
    sim.advance(40)
    assert 8 < queue_slope(sim.samples(6)) < 12      # поток около 10 задач/с


def test_isolation_forest_false_positive_rate_is_bounded(cfg):
    sim = ServiceSimulator(seed=1)
    sim.advance(cfg.period_s * 400)
    model = AnomalyModel(quantile=cfg.anomaly_quantile).fit(sim.samples(400))
    sim2 = ServiceSimulator(seed=2)                  # новая нормальная выборка
    sim2.advance(cfg.period_s * 300)
    s = sim2.samples(300)
    fp = sum(model.is_anomaly(s[i - 6:i]) for i in range(6, 300)) / 294
    assert fp < 0.05
    sim2.inject("workers_crash")
    sim2.advance(30)
    assert model.is_anomaly(sim2.samples(6))


def test_anomaly_path_creates_incident_without_rule_match(cfg):
    system = build_system(anomaly=True)
    system.sim.inject("sensitive_data")              # метрики в норме, правило D5 сработает
    run = system.run_until_incident()
    assert run is not None and run.incident.rule == "D5"
