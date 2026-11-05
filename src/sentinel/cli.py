"""Командная строка Sentinel.

    sentinel list | run <сценарий> | all          сценарии золотого набора на имитаторе
    sentinel kb                                   проверка и статистика базы знаний
    sentinel eval retrieval | e2e | perf          эксперименты раздела 3 (JSON в docs/results)
    sentinel serve                                REST и веб-панель дежурного
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from sentinel.audit import build_report
from sentinel.domain import State
from sentinel.knowledge import HashingEmbedder, OllamaEmbedder, load_runbooks, problems
from sentinel.llm import OllamaClient
from sentinel.scenarios import SCENARIOS, run_scenario
from sentinel.system import DEFAULT_RUNBOOKS
from sentinel.tools import default_registry

RESULTS = Path(__file__).resolve().parents[2] / "docs" / "results"


def _llm(args):
    if args.llm != "ollama":
        return None
    return OllamaClient(args.model, host=args.ollama, timeout_s=args.timeout)


def _embedder(args):
    if args.embedder == "hashing":
        return None                                       # значение по умолчанию в HybridRetriever
    return OllamaEmbedder(args.embedder, host=args.ollama)


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--llm", choices=["stub", "ollama"], default="stub")
    p.add_argument("--model", default="qwen2.5:3b-instruct")
    p.add_argument("--embedder", default="hashing", help="hashing (заглушка) или модель Ollama, напр. bge-m3")
    p.add_argument("--ollama", default="http://localhost:11434")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--mode", choices=["hybrid", "rules_only", "llm_only"], default="hybrid")
    p.add_argument("--seed", type=int, default=7)


def cmd_scenarios(args) -> int:
    if args.command == "list":
        for key, sc in SCENARIOS.items():
            print(f"{key:<4} {sc.id:<9} {sc.group:<9} {sc.title}")
        return 0
    keys = list(SCENARIOS) if args.command == "all" else [args.scenario]
    llm, embedder = _llm(args), _embedder(args)
    failed = 0
    for key in keys:
        sc = SCENARIOS[key]
        if not sc.applies_to(args.mode):
            print(f"[SKIP] {sc.id:<9} не применим в режиме {args.mode}")
            continue
        res = run_scenario(sc, llm, args.mode, seed=args.seed, embedder=embedder)
        run = res.run
        state = run.state.value if run else "инцидент не создан"
        extra = f"  ({run.reason})" if run and run.state is State.ESCALATED else ""
        print(f"[{'PASS' if res.ok else 'FAIL'}] {sc.id:<9} {sc.title:<38} -> {state}{extra}")
        if args.command == "run" and run:
            print(build_report(res.system.store, run.incident.id))
        failed += not res.ok
    return 1 if failed else 0


def cmd_kb(args) -> int:
    kb = load_runbooks(DEFAULT_RUNBOOKS)
    found = problems(kb, default_registry())
    print(f"Инструкций: {len(kb)}; по сервисам: {dict(Counter(r.service for r in kb))}")
    print(f"Автоматически исполнимых (есть критерии успеха): {sum(bool(r.success_criteria) for r in kb)}")
    for p in found:
        print(f"  ОШИБКА: {p}")
    print("База знаний согласована." if not found else f"Найдено нарушений: {len(found)}")
    return 1 if found else 0


def cmd_eval(args) -> int:
    from sentinel.eval import save

    out = Path(args.out) if args.out else RESULTS / f"{args.what}.json"
    if args.what == "retrieval":
        from sentinel.eval.retrieval import evaluate, load_queries

        embedders = {"hashing": HashingEmbedder()}
        if args.embedder != "hashing":
            embedders[args.embedder] = OllamaEmbedder(args.embedder, host=args.ollama)
        result = evaluate(load_runbooks(DEFAULT_RUNBOOKS), load_queries(), embedders)
        for r in result["rows"]:
            print(f"{r['config']:<34} prefilter={r['prefilter']!s:<5} Hit@1={r['hit1']:.2f} "
                  f"Hit@3={r['hit3']:.2f} MRR={r['mrr']:.2f} {r['latency_ms']:.1f} мс")
    elif args.what == "e2e":
        from sentinel.eval.e2e import evaluate

        llm = _llm(args)
        meta = {"llm": llm.describe() if llm else "stub", "embedder": args.embedder}
        result = evaluate(args.modes.split(","), [int(s) for s in args.seeds.split(",")],
                          llm_factory=(lambda: llm) if llm else None, embedder=_embedder(args),
                          keys=args.keys.split(",") if args.keys else None, meta=meta,
                          progress=lambda r: print(f"  {r['mode']:<10} seed={r['seed']} {r['id']:<9} "
                                                   f"{'PASS' if r['ok'] else 'FAIL'} {r['state']} "
                                                   f"{r['reason']} diag={r['diagnosis']}", flush=True))
        for mode, s in result["summary"].items():
            print(f"{mode:<10} pass={s['passed']}/{s['runs']} diag={s['diag_accuracy']} "
                  f"auto={s['autonomous_share']:.2f} unsafe={s['unsafe_runs']} wrong={s['wrong_actions']}")
    else:
        from sentinel.eval.perf import evaluate

        emb = _embedder(args)
        result = evaluate(load_runbooks(DEFAULT_RUNBOOKS), emb)
        for row in result["kb_scaling"]:
            print(row)
        print(result["detector"], result.get("query_embedding"))
    print(f"Результат: {save(result, out)}")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from sentinel.api import create_app
    from sentinel.system import build_system

    system = build_system(llm=_llm(args), mode=args.mode, embedder=_embedder(args), seed=args.seed)
    uvicorn.run(create_app(system), host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sentinel", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p = sub.add_parser("run")
    p.add_argument("scenario", choices=list(SCENARIOS))
    _common(p)
    _common(sub.add_parser("all"))
    sub.add_parser("kb")
    p = sub.add_parser("eval")
    p.add_argument("what", choices=["retrieval", "e2e", "perf"])
    p.add_argument("--modes", default="hybrid,rules_only,llm_only")
    p.add_argument("--seeds", default="1,2,3")
    p.add_argument("--keys", default="", help="подмножество сценариев через запятую")
    p.add_argument("--out", default="")
    _common(p)
    p = sub.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    _common(p)
    args = ap.parse_args(argv)
    if args.command in ("list", "run", "all"):
        return cmd_scenarios(args)
    return {"kb": cmd_kb, "eval": cmd_eval, "serve": cmd_serve}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
