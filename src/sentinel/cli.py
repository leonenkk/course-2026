"""Командная строка: запуск сценариев на каркасе системы."""
from __future__ import annotations

import argparse
import sys

from sentinel.audit import build_report
from sentinel.domain import State
from sentinel.llm import OllamaClient, StubLLM
from sentinel.scenarios import SCENARIOS, Scenario
from sentinel.system import System, build_system


def run_scenario(sc: Scenario, llm=None, mode: str = "hybrid") -> tuple[System, object, bool]:
    llm = llm or StubLLM(obedient=sc.llm_obedient)
    approver = (lambda inc, sh: sc.approve) if sc.approve is not None else None
    system = build_system(llm=llm, mode=mode, approver=approver)
    for _ in range(12):                                   # спокойная работа перед сбоем
        system.tick()
    system.sim.inject(sc.fault, injection=sc.injection)
    run = system.run_until_incident(max_ticks=40)
    ok = _check(sc, system, run)
    return system, run, ok


def _check(sc: Scenario, system: System, run) -> bool:
    if not sc.expect_incident:
        return run is None
    if run is None or run.state is not sc.expect_state:
        return False
    executed = [a for a, _ in system.sim.executed]
    if sc.expect_action and sc.expect_action not in executed:
        return False
    return not any(a in executed for a in sc.forbidden_actions)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sentinel", description=__doc__)
    ap.add_argument("command", choices=["list", "run", "all"])
    ap.add_argument("scenario", nargs="?", choices=sorted(SCENARIOS))
    ap.add_argument("--llm", choices=["stub", "ollama"], default="stub")
    ap.add_argument("--model", default="qwen2.5:3b-instruct")
    ap.add_argument("--mode", choices=["hybrid", "rules_only"], default="hybrid")
    args = ap.parse_args(argv)

    if args.command == "list":
        for key, sc in SCENARIOS.items():
            print(f"{key:<4} {sc.id:<9} {sc.title}")
        return 0
    llm = OllamaClient(args.model) if args.llm == "ollama" else None
    keys = sorted(SCENARIOS) if args.command == "all" else [args.scenario or "c1"]
    failed = 0
    for key in keys:
        sc = SCENARIOS[key]
        system, run, ok = run_scenario(sc, llm, args.mode)
        state = run.state.value if run else "инцидент не создан"
        print(f"[{'PASS' if ok else 'FAIL'}] {sc.id:<9} {sc.title:<42} -> {state}"
              f"{'  (' + run.reason + ')' if run and run.state is State.ESCALATED else ''}")
        if args.command == "run" and run:
            print(build_report(system.store, run.incident.id))
        failed += not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
