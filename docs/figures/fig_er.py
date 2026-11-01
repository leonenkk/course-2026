from _draw import Canvas, SYM, EXT, STO, WHITE
import matplotlib.pyplot as plt

ROW = 0.42
HEAD = 0.65


def entity(c, x, ytop, w, name, attrs, style=SYM, ls="-"):
    """x --- левый край, ytop --- верхний край; возвращает словарь с границами."""
    h = HEAD + ROW * len(attrs) + 0.12
    c.rect(x, ytop - h, x + w, ytop, style=style, ls=ls, lw=1.0, z=2, fc="white")
    c.rect(x, ytop - HEAD, x + w, ytop, style=style, ls=ls, lw=1.0, z=3)
    c.text(x + w / 2, ytop - HEAD / 2, name, fs=9, bold=True, bg=False, z=5)
    for i, a in enumerate(attrs):
        yy = ytop - HEAD - ROW * (i + 0.6)
        key = ""
        if a.startswith(("PK ", "FK ", "UQ ")):
            key, a = a[:2], a[3:]
        if key:
            c.text(x + 0.12, yy, key, fs=7, ha="left", bold=True, bg=False, z=5, color="#7a1f1f")
        c.text(x + 0.62, yy, a, fs=8, ha="left", bg=False, z=5)
    return dict(l=x, r=x + w, t=ytop, b=ytop - h, cx=x + w / 2, cy=ytop - h / 2)


def card(c, x, y, s, ha="center"):
    c.text(x, y, s, fs=7.6, bg=True, ha=ha, z=7)


def build(out):
    W = 4.6
    A, B, C_ = 0.3, 5.95, 11.6
    c = Canvas(16.5, 13.9, y0=0.8)

    inc = entity(c, A, 14.4, W, "Incident", ["PK id", "service", "signature", "source", "status", "opened_at",
                                              "closed_at"])
    sig = entity(c, B, 14.4, W, "IncidentSignal", ["PK incident_id", "PK signal_id", "value", "observed_at"])
    rb = entity(c, C_, 14.4, W, "Runbook (файл Markdown)",
                ["PK id", "title", "service", "signals_required[]", "signals_excluded[]", "actions[]",
                 "success_criteria[]"],
                style=STO, ls="--")
    aud = entity(c, A, 9.8, W, "AuditEvent", ["PK id", "FK incident_id", "seq", "ts", "actor", "type",
                                               "payload (JSON)", "prev_hash", "hash"])
    dia = entity(c, B, 10.8, W, "Diagnosis", ["PK id", "FK incident_id", "FK runbook_id", "cause", "c_llm",
                                               "s_ret", "m_sig", "confidence", "model"])
    apr = entity(c, C_, 9.2, W, "Approval", ["PK id", "FK decision_id", "approver", "verdict", "decided_at"])
    pol = entity(c, B, 5.1, W, "PolicyDecision", ["PK id", "FK diagnosis_id", "FK action", "params (JSON)",
                                                   "verdict", "fired_rules[]"])
    exe = entity(c, C_, 5.5, W, "Execution", ["PK id", "FK decision_id", "UQ idem_key", "status",
                                               "result (JSON)", "started_at"])
    act = entity(c, A, 4.1, W, "ActionSpec (реестр)", ["PK name", "risk", "params_schema", "timeout_s",
                                                        "idempotent"], style=STO, ls="--")

    # Incident -- IncidentSignal
    c.line([(inc["r"], 13.5), (sig["l"], 13.5)], arrow=False)
    card(c, 5.5, 13.75, "1"); card(c, 5.65, 13.25, "1..*")
    # Incident -- AuditEvent
    c.line([(inc["cx"], inc["b"]), (inc["cx"], aud["t"])], arrow=False)
    card(c, inc["cx"] + 0.3, inc["b"] - 0.25, "1"); card(c, inc["cx"] + 0.4, aud["t"] + 0.25, "0..*")
    # Incident -- Diagnosis
    c.line([(inc["r"], 12.2), (5.45, 12.2), (5.45, dia["t"] - 0.5), (dia["l"], dia["t"] - 0.5)], arrow=False)
    card(c, 5.1, 12.45, "1"); card(c, 5.5, dia["t"] - 0.15, "1..*")
    # Diagnosis -- Runbook
    c.line([(dia["r"], 9.9), (11.1, 9.9), (11.1, 13.0), (rb["l"], 13.0)], arrow=False, ls="--")
    card(c, 10.85, 10.15, "*"); card(c, 11.35, 13.25, "1")
    # Diagnosis -- PolicyDecision
    c.line([(dia["cx"], dia["b"]), (dia["cx"], pol["t"])], arrow=False)
    card(c, dia["cx"] + 0.3, dia["b"] - 0.25, "1"); card(c, dia["cx"] + 0.4, pol["t"] + 0.25, "1..*")
    # PolicyDecision -- ActionSpec
    c.line([(pol["l"], 3.4), (act["r"], 3.4)], arrow=False, ls="--")
    card(c, 5.7, 3.65, "*"); card(c, 5.15, 3.65, "1")
    # PolicyDecision -- Approval
    c.line([(pol["r"], 4.6), (11.1, 4.6), (11.1, 7.0), (apr["l"], 7.0)], arrow=False)
    card(c, 10.8, 4.85, "1"); card(c, 11.35, 7.25, "0..*")
    # PolicyDecision -- Execution
    c.line([(pol["r"], 3.3), (exe["l"], 3.3)], arrow=False)
    card(c, 10.8, 3.55, "1"); card(c, 11.35, 3.55, "0..1")
    c.save(out)


if __name__ == "__main__":
    import sys
    build(sys.argv[1])
