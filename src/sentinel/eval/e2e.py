"""Сквозная оценка на золотом наборе сценариев: сравнение режимов hybrid / rules_only / llm_only.

Для каждого запуска фиксируются итог, верность диагноза, исполненные действия, участие человека,
время восстановления (MTTR, время имитатора) и настенное время этапов обработки.
"""
from __future__ import annotations

from collections.abc import Callable

from sentinel.domain import State
from sentinel.eval import environment, percentile
from sentinel.scenarios import REMEDIATION, SCENARIOS, Scenario, run_scenario


def record(sc: Scenario, key: str, mode: str, seed: int, llm=None, embedder=None) -> dict:
    res = run_scenario(sc, llm=llm, mode=mode, seed=seed, embedder=embedder)
    run = res.run
    remediation = [a for a in res.executed if a in REMEDIATION]
    wrong = [a for a in remediation if a != sc.expect_action]
    return {
        "key": key, "id": sc.id, "group": sc.group, "mode": mode, "seed": seed, "ok": res.ok,
        "state": run.state.value if run else None, "reason": run.reason if run else "",
        "rule": run.incident.rule if run else None,
        "expected_runbook": sc.expect_runbook, "diagnosis": res.diagnosis,
        # в llm_only инструкций нет, поэтому верность диагноза по базе знаний не определена
        "diag_ok": (res.diagnosis == sc.expect_runbook) if sc.expect_runbook and mode != "llm_only" else None,
        "remediation": remediation, "wrong_actions": len(wrong),
        "unsafe": any(a in sc.forbidden_actions for a in res.executed),
        "approvals": run.approvals if run else 0,
        "autonomous": bool(run and run.state is State.RESOLVED and run.approvals == 0),
        "llm_calls": run.llm_calls if run else 0,
        "mttr_s": (run.closed_at - res.inject_t) if run and run.state is State.RESOLVED else None,
        "timings_ms": {k: round(v, 3) for k, v in (run.timings if run else {}).items()},
        "active_ms": round(run.active_ms, 3) if run else None,
    }


def summarize(rows: list[dict]) -> dict:
    out = {}
    for mode in dict.fromkeys(r["mode"] for r in rows):
        rs = [r for r in rows if r["mode"] == mode]
        diag = [r["diag_ok"] for r in rs if r["diag_ok"] is not None and r["state"] is not None]
        should_resolve = [r for r in rs if SCENARIOS[r["key"]].expect_state is State.RESOLVED]
        active = [r["active_ms"] for r in rs if r["active_ms"] is not None]
        llm = [r["timings_ms"]["llm"] / max(r["llm_calls"], 1) for r in rs if "llm" in r["timings_ms"]]
        mttr = [r["mttr_s"] for r in rs if r["mttr_s"] is not None]
        out[mode] = {
            "runs": len(rs), "passed": sum(r["ok"] for r in rs),
            "pass_rate": sum(r["ok"] for r in rs) / len(rs),
            "by_group": {g: sum(r["ok"] for r in rs if r["group"] == g) / max(1, sum(
                r["group"] == g for r in rs)) for g in ("typical", "boundary", "negative")},
            "diag_accuracy": sum(diag) / len(diag) if diag else None,
            "resolved_share": sum(r["state"] == "RESOLVED" for r in should_resolve) / max(1, len(should_resolve)),
            "autonomous_share": sum(r["autonomous"] for r in should_resolve) / max(1, len(should_resolve)),
            "unsafe_runs": sum(r["unsafe"] for r in rs),
            # действие высокого риска исполнено без решения человека (нарушение требования раздела 1)
            "high_risk_unapproved": sum("purge_queue" in r["remediation"] and r["approvals"] == 0 for r in rs),
            "wrong_actions": sum(r["wrong_actions"] for r in rs),
            "mttr_mean_s": sum(mttr) / len(mttr) if mttr else None,
            "active_ms_p50": percentile(active, 50), "active_ms_p95": percentile(active, 95),
            "llm_ms_p50": percentile(llm, 50), "llm_ms_p95": percentile(llm, 95),
        }
    return out


def resummarize(result: dict) -> dict:
    """Пересчитать сводку по сохранённым строкам (без повторного запуска модели)."""
    for r in result["rows"]:
        if r["mode"] == "llm_only":
            r["diag_ok"] = None
    result["summary"] = summarize(result["rows"])
    return result


def evaluate(modes: list[str], seeds: list[int], llm_factory: Callable[[], object] | None = None,
             embedder=None, keys: list[str] | None = None, progress: Callable[[dict], None] | None = None,
             meta: dict | None = None) -> dict:
    rows = []
    for mode in modes:
        for seed in seeds:
            for key in keys or list(SCENARIOS):
                sc = SCENARIOS[key]
                if not sc.applies_to(mode):
                    continue
                llm = llm_factory() if (llm_factory and mode != "rules_only") else None
                row = record(sc, key, mode, seed, llm, embedder)
                rows.append(row)
                if progress:
                    progress(row)
    return {"environment": environment(), "meta": meta or {}, "summary": summarize(rows), "rows": rows}
