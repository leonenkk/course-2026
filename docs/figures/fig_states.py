from matplotlib.patches import Circle

from _draw import Canvas, SYM, NEU, STO

GREEN = dict(fc="#d9efd5", ec="#2f5d2a")
RED = dict(fc="#f8d9d6", ec="#8c2a22")


def state(c, x, y, name, sub, st=SYM, w=2.6, h=1.1):
    c.box(x, y, w, h, name, style=st, bold=True, sub=sub, fs=8.8, fs_sub=7.6, rounded=0.25)


def build(out):
    c = Canvas(16.5, 11.9, y0=0.3)
    c.rect(0.3, 2.6, 16.2, 11.6, style=dict(fc="#fafafa", ec="#555555"), ls="--", lw=0.9, z=0)
    c.text(0.55, 11.2, "Обработка инцидента (активные состояния)", fs=8.6, bold=True, ha="left", bg=False)

    ym = 7.6
    xs = [1.7, 5.9, 10.1, 14.3]
    for x, n, sub in zip(xs, ("NEW", "DIAGNOSING", "PLANNED", "ACTING"),
                         ("создан", "диагностика", "решение выбрано", "выполнение действия")):
        state(c, x, ym, n, sub)
    state(c, 12.2, 10.2, "AWAITING_APPROVAL", "ожидание человека", st=NEU, w=3.7)
    state(c, 14.3, 4.7, "VERIFYING", "проверка результата")
    state(c, 14.3, 1.2, "RESOLVED", "закрыт", st=GREEN, w=2.4)
    state(c, 3.0, 1.2, "ESCALATED", "передан человеку", st=RED, w=4.4)

    # начальное состояние
    c.ax.add_patch(Circle((1.7, 9.7), 0.17, fc="black", zorder=3))
    c.line([(1.7, 9.53), (1.7, ym + 0.55)])

    # основной путь
    for (a, b, t) in ((0, 1, "запуск"), (1, 2, "диагноз\nпроверен"), (2, 3, "AUTO_\nEXECUTE")):
        c.line([(xs[a] + 1.3, ym), (xs[b] - 1.3, ym)])
        c.text((xs[a] + xs[b]) / 2, ym + 0.5, t, fs=7.8, italic=True, bg=False)

    # PLANNED -> AWAITING -> ACTING
    c.line([(10.8, ym + 0.55), (11.2, 9.65)])
    c.text(10.65, 8.75, "REQUIRE_\nAPPROVAL", fs=7.8, italic=True, ha="right", bg=False)
    c.line([(13.2, 9.65), (13.9, ym + 0.55)])
    c.text(14.2, 8.8, "approve", fs=7.8, italic=True, ha="left", bg=False)

    # ACTING -> VERIFYING
    c.line([(14.3, ym - 0.55), (14.3, 4.7 + 0.55)])
    c.text(14.45, 6.2, "действие\nвыполнено", fs=7.8, italic=True, ha="left", bg=False)
    # VERIFYING -> PLANNED
    c.line([(14.3 - 1.3, 4.9), (10.6, 4.9), (10.6, ym - 0.55)], lw=0.9, ls="--")
    c.text(10.5, 5.95, "критерии не выполнены,\nесть следующая гипотеза", fs=7.8, italic=True,
           ha="right", bg=False)
    # VERIFYING -> RESOLVED
    c.line([(14.3, 4.7 - 0.55), (14.3, 1.2 + 0.55)])
    c.text(14.45, 3.3, "критерии\nуспеха\nвыполнены", fs=7.8, italic=True, ha="left", bg=False)
    # любое активное состояние -> ESCALATED
    c.line([(3.0, 2.6), (3.0, 1.2 + 0.55)])
    c.text(5.4, 1.65, "из любого активного состояния: нет знаний или сбой LLM;\n"
           "отказ верификатора; вердикт ESCALATE или DENY;\n"
           "reject или таймаут подтверждения; сбой исполнения;\n"
           "гипотезы исчерпаны", fs=7.8, italic=True, ha="left", bg=False)
    c.save(out)


if __name__ == "__main__":
    import sys
    build(sys.argv[1])
