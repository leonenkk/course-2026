"""Графики результатов экспериментов раздела 3 (по JSON из docs/results).

Запуск:  python fig_results.py <каталог JSON> <каталог для PNG>
Цвета прошли проверку различимости (в том числе при нарушениях цветового зрения); на каждом
графике значения подписаны, поэтому цвет не является единственным носителем информации.
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

plt.rcParams.update({"font.family": "Liberation Serif", "font.size": 10, "axes.unicode_minus": False})
CM = 1 / 2.54
C1, C2, C3 = "#1f4e9c", "#2a9d8f", "#d1792b"
INK, MUTED, GRID = "#222222", "#555555", "#d9d9d9"
COMMA = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))     # десятичная запятая (ГОСТ)


def _axes(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=INK)
    ax.set_axisbelow(True)


def retrieval(data: dict, out: Path) -> None:
    rows = data["rows"]
    names = list(dict.fromkeys(r["config"] for r in rows))
    on = {r["config"]: r["mrr"] for r in rows if r["prefilter"]}
    off = {r["config"]: r["mrr"] for r in rows if not r["prefilter"]}
    fig, ax = plt.subplots(figsize=(16.5 * CM, 8.5 * CM))
    y = range(len(names))
    h = 0.38
    b1 = ax.barh([i - h / 2 for i in y], [on[n] for n in names], h - 0.04, color=C1, label="с предфильтром")
    b2 = ax.barh([i + h / 2 for i in y], [off[n] for n in names], h - 0.04, color=C2, label="без предфильтра")
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_width() + 0.01, b.get_y() + b.get_height() / 2, f"{b.get_width():.2f}".replace(".", ","),
                    va="center", fontsize=8.5, color=INK)
    ax.set_yticks(list(y), names)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.08)
    ax.set_xlabel("MRR (средний обратный ранг верной инструкции)")
    ax.xaxis.grid(True, color=GRID, lw=0.6)
    ax.xaxis.set_major_formatter(COMMA)
    _axes(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.35, -0.16), ncol=2, frameon=False)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def modes(summary: dict, out: Path) -> None:
    labels = {"hybrid": "гибридный", "rules_only": "только символьный", "llm_only": "только модель"}
    metrics = [("pass_rate", "Пройдено\nсценариев"), ("diag_accuracy", "Верный\nдиагноз"),
               ("resolved_share", "Устранено\n(всего)"), ("autonomous_share", "Устранено\nавтономно")]
    fig, ax = plt.subplots(figsize=(16.5 * CM, 7.5 * CM))
    present = [m for m in ("hybrid", "rules_only", "llm_only") if m in summary]
    w = 0.8 / len(present)
    for k, (mode, color) in enumerate(zip(present, (C1, C2, C3), strict=False)):
        xs = [i + (k - (len(present) - 1) / 2) * w for i in range(len(metrics))]
        raw = [summary[mode][m] for m, _ in metrics]
        bars = ax.bar(xs, [v or 0.0 for v in raw], w - 0.03, color=color, label=labels[mode])
        for b, v in zip(bars, raw, strict=True):
            text = "н/д" if v is None else f"{v:.2f}".replace(".", ",")      # нет базы знаний --- нет диагноза
            ax.text(b.get_x() + b.get_width() / 2, (v or 0.0) + 0.015, text, ha="center", fontsize=8, color=INK)
    ax.set_xticks(range(len(metrics)), [t for _, t in metrics])
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Доля")
    ax.yaxis.set_major_formatter(COMMA)
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    _axes(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, frameon=False)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def scaling(perf: dict, out: Path) -> None:
    rows = perf["kb_scaling"]
    n = [r["runbooks"] for r in rows]
    fig, ax = plt.subplots(figsize=(16.5 * CM, 7.5 * CM))
    ax.plot(n, [r["rank_all_ms_p50"] for r in rows], color=C1, lw=2, marker="o", ms=5,
            label="ранжирование всей базы")
    ax.plot(n, [r["prefiltered_ms_p50"] for r in rows], color=C3, lw=2, marker="s", ms=5,
            label="с символьным предфильтром")
    emb = perf.get("query_embedding")
    if emb:
        ax.axhline(emb["query_ms_p50"], color=MUTED, lw=1, ls="--")
        ax.text(n[0], emb["query_ms_p50"] * 1.25, f"эмбеддинг запроса ({emb['embedder']}), "
                f"{emb['query_ms_p50']:.0f} мс".replace(".", ","), fontsize=8.5, color=MUTED)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Число инструкций в базе знаний")
    ax.set_ylabel("Время поиска, мс (медиана)")
    ax.xaxis.set_major_formatter(COMMA)
    ax.yaxis.set_major_formatter(COMMA)
    ax.set_ylim(top=emb["query_ms_p50"] * 3 if emb else None)
    ax.grid(True, which="major", color=GRID, lw=0.6)
    _axes(ax)
    ax.legend(loc="center left", bbox_to_anchor=(0.0, 0.55), frameon=False)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)
    retrieval(json.loads((src / "retrieval.json").read_text()), dst / "fig_eval_retrieval.png")
    scaling(json.loads((src / "perf.json").read_text()), dst / "fig_eval_scaling.png")
    summary = {}
    stub = src / "e2e_rules_bge.json"
    real = src / "e2e_qwen3b.json"
    if stub.exists():
        summary["rules_only"] = json.loads(stub.read_text())["summary"]["rules_only"]
    if real.exists():
        summary.update(json.loads(real.read_text())["summary"])
    if summary:
        modes(summary, dst / "fig_eval_modes.png")
    print("OK")
