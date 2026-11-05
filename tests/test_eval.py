"""Дымовые тесты стенда оценки (на тестовых двойниках, без нейросетей)."""
from sentinel.eval import percentile
from sentinel.eval.e2e import evaluate as e2e
from sentinel.eval.perf import kb_scaling
from sentinel.eval.retrieval import evaluate as retrieval
from sentinel.eval.retrieval import load_queries


def test_query_set_refers_to_existing_runbooks(runbooks):
    ids = {r.id for r in runbooks}
    queries = load_queries()
    assert len(queries) >= 40 and all(q.expected in ids for q in queries)
    assert {q.kind for q in queries} == {"logs", "paraphrase", "english"}


def test_retrieval_eval_reports_metrics(runbooks):
    res = retrieval(runbooks, load_queries())
    row = next(r for r in res["rows"] if r["config"].startswith("Гибрид") and r["prefilter"])
    assert 0 < row["hit1"] <= row["hit3"] <= 1 and row["mrr"] > 0.5


def test_e2e_eval_compares_modes():
    res = e2e(["hybrid", "llm_only"], [1], keys=["c1", "c6"])
    s = res["summary"]
    assert s["hybrid"]["pass_rate"] == 1.0 and s["hybrid"]["unsafe_runs"] == 0
    assert s["llm_only"]["unsafe_runs"] >= 1


def test_kb_scaling_measures_growth(runbooks):
    rows = kb_scaling(runbooks, sizes=(24, 240), repeat=3)
    assert rows[1]["vectors_kb"] == 10 * rows[0]["vectors_kb"]


def test_percentile():
    assert percentile([], 50) is None and percentile([5.0], 95) == 5.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5
