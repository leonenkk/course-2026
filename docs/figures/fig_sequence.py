from _draw import Canvas, SYM, NEU, EXT, STO, WHITE


def build(out):
    H = 18.0
    c = Canvas(16.5, H)
    xs = {"svc": 1.05, "det": 3.15, "agent": 5.35, "kb": 7.55, "llm": 9.7, "pol": 12.0, "exe": 14.0, "duty": 15.7}
    names = {
        "svc": ("Демо-\nсервис", EXT), "det": ("Детектор", SYM), "agent": ("Агент\n(оркестратор)", SYM),
        "kb": ("База знаний\nи поиск", NEU), "llm": ("Языковая\nмодель", NEU),
        "pol": ("Верификатор\nи политика", SYM), "exe": ("Исполни-\nтель", SYM), "duty": ("Дежур-\nный", EXT),
    }
    top = H - 1.0
    for k, x in xs.items():
        t, st = names[k]
        c.box(x, top, 1.7 if k not in ("duty",) else 1.4, 1.2, t, style=st, fs=8.2, rounded=0.12)
        c.line([(x, top - 0.6), (x, 0.5)], arrow=False, ls=(0, (4, 3)), lw=0.7, color="#555555", z=1)

    y = top - 1.35
    step = 0.82
    n = [0]

    def msg(a, b, text, dashed=False, dy=None, num=True, self_loop=False):
        nonlocal y
        if num:
            n[0] += 1
            label = f"{n[0]}. {text}"
        else:
            label = text
        x0, x1 = xs[a], xs[b]
        if self_loop:
            c.line([(x0, y + 0.18), (x0 + 0.9, y + 0.18), (x0 + 0.9, y - 0.18), (x0, y - 0.18)], lw=0.9)
            c.text(x0 + 1.0, y, label, fs=7.8, ha="left", bg=True)
        else:
            c.line([(x0, y), (x1, y)], ls="--" if dashed else "-", lw=0.9)
            c.text((x0 + x1) / 2, y + 0.24, label, fs=7.8, bg=True)
        y -= step if dy is None else dy

    msg("svc", "det", "метрики и логи (каждые 5 с)")
    msg("det", "det", "правила и аномалия: WORKERS_DOWN,\nQUEUE_GROWING", self_loop=True, dy=1.0)
    msg("det", "agent", "Incident")
    msg("agent", "agent", "сбор контекста,\nмаркировка недоверенного текста", self_loop=True, dy=1.0)
    msg("agent", "kb", "запрос по сигналам и симптомам")
    msg("kb", "agent", "top-3 runbook: BM25 + вектор, RRF", dashed=True)
    msg("agent", "llm", "контекст, фрагменты runbook, схема ответа")
    msg("llm", "agent", "JSON: гипотезы, действие, $c_{\\mathrm{LLM}}$", dashed=True)
    msg("agent", "pol", "проверка гипотезы, расчёт C, правила")
    msg("pol", "agent", "вердикт: AUTO_EXECUTE", dashed=True, dy=0.75)

    # альтернативный фрагмент: подтверждение человеком
    fy0 = y + 0.2
    c.rect(0.55, fy0 - 2.15, 16.2, fy0, style=dict(fc="none", ec="#555555"), ls="-", lw=0.8, z=1, fc="none")
    c.text(0.85, fy0 - 0.25, "alt", fs=8, bold=True, bg=False)
    c.text(1.3, fy0 - 0.25, "[вердикт = REQUIRE_APPROVAL]", fs=7.8, ha="left", bg=False, italic=True)
    y = fy0 - 0.85
    msg("agent", "duty", "запрос подтверждения", num=False)
    msg("duty", "agent", "approve / reject", dashed=True, num=False, dy=1.0)
    y = fy0 - 2.15 - 0.55

    msg("agent", "exe", "restart_workers (ключ идемпотентности)")
    msg("exe", "svc", "перезапуск воркеров")
    msg("svc", "agent", "метрики через $T_{\\mathrm{v}}$: очередь убывает", dashed=True)
    msg("agent", "agent", "критерии успеха runbook выполнены", self_loop=True, dy=1.0)
    msg("agent", "duty", "отчёт об инциденте (RESOLVED)")
    c.text(8.25, 0.25, "Каждый шаг фиксируется в журнале аудита (запись события с хэшем предыдущей).",
           fs=7.8, italic=True, bg=False)
    c.save(out)


if __name__ == "__main__":
    import sys
    build(sys.argv[1])
