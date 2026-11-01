from _draw import Canvas, SYM, NEU, WHITE

GREEN = dict(fc="#d9efd5", ec="#2f5d2a")
RED = dict(fc="#f8d9d6", ec="#8c2a22")


def build(out):
    c = Canvas(16.5, 19.3)
    X, PW, PH = 4.6, 6.4, 0.85       # левая колонка: центр, ширина и высота блока
    DW, DH = 4.8, 1.15               # ромбы
    XM = 11.0                        # средняя колонка
    BUS = 15.7                       # шина эскалации

    def proc(y, text, st=SYM, x=X, w=PW, h=PH):
        c.box(x, y, w, h, text, style=st, fs=8.4, rounded=0.15)

    def dec(y, text, x=X):
        c.diamond(x, y, DW, DH, text, fs=8.2)

    ys = dict(T0=18.55, P1=17.35, D1=15.85, P2=14.35, D2=13.0, P3=11.55, D3=10.25, P4=8.95,
              D4a=7.75, D4b=6.3, P5=4.85, P6=3.8, D5=2.6, D6=1.1)

    c.terminator(X, ys["T0"], 4.4, 0.7, "Начало: получен Incident", fs=8.4)
    proc(ys["P1"], "Сбор контекста, поиск runbook\n(BM25 и вектор, слияние RRF)", NEU)
    dec(ys["D1"], "Релевантные\nrunbook найдены?")
    proc(ys["P2"], "Запрос к LLM по JSON-схеме\n(до 2 повторов при ошибке формата)", NEU)
    dec(ys["D2"], "Ответ соответствует\nсхеме?")
    proc(ys["P3"], "Верификация гипотезы $h_i$,\nрасчёт уверенности $C$")
    dec(ys["D3"], "Верификация\nпройдена?")
    proc(ys["P4"], "Движок политик: вердикт", h=0.7)
    dec(ys["D4a"], "ESCALATE\nили DENY?")
    dec(ys["D4b"], "REQUIRE_\nAPPROVAL?")
    proc(ys["P5"], "Идемпотентное выполнение\nдействия (таймаут, аудит)")
    proc(ys["P6"], "Пауза $T_v$, проверка\nкритериев успеха")
    dec(ys["D5"], "Критерии\nвыполнены?")
    dec(ys["D6"], "Есть гипотеза и\nне исчерпан лимит?")

    # средняя колонка
    proc(ys["D4b"], "Запрос подтверждения\nдежурному", x=XM, w=4.2)
    c.diamond(XM, ys["P5"], 3.6, 1.15, "Одобрено?", fs=8.2)
    c.terminator(XM, ys["D5"], 4.2, 0.8, "RESOLVED: закрыть инцидент,\nсформировать отчёт", style=GREEN, fs=8.2)
    c.terminator(XM, ys["D6"], 4.2, 0.8, "ESCALATED: уведомление,\nтикет и отчёт", style=RED, fs=8.2)

    def half(key, h):
        return {"P": h / 2, "D": DH / 2}[key[0]]

    order = ["T0", "P1", "D1", "P2", "D2", "P3", "D3", "P4", "D4a", "D4b", "P5", "P6", "D5", "D6"]
    hh = {"T0": 0.35, "P4": 0.35}
    for a, b in zip(order[:-1], order[1:]):
        ha = hh.get(a, PH / 2 if a[0] == "P" else DH / 2)
        hb = hh.get(b, PH / 2 if b[0] == "P" else DH / 2)
        c.line([(X, ys[a] - ha), (X, ys[b] + hb)], lw=0.9)

    def lab(x, y, t, ha="center"):
        c.text(x, y, t, fs=7.8, italic=True, ha=ha, bg=True)

    # подписи на выходах из ромбов вниз
    for k in ("D1", "D2", "D3", "D5"):
        lab(X + 0.35, ys[k] - DH / 2 - 0.2, "да", ha="left")
    lab(X + 0.45, ys["D4a"] - DH / 2 - 0.15, "нет", ha="left")
    lab(X + 0.35, ys["D4b"] - DH / 2 - 0.22, "нет (AUTO_EXECUTE)", ha="left")
    lab(X + 0.35, ys["D5"] - DH / 2 - 0.2, "нет", ha="left")

    # «нет» на шину эскалации
    for k, label in (("D1", "нет"), ("D2", "нет"), ("D3", "нет"), ("D4a", "да")):
        c.line([(X + DW / 2, ys[k]), (BUS, ys[k])], lw=0.9, arrow=False)
        lab(X + DW / 2 + 0.55, ys[k] + 0.2, label)
    # подтверждение
    c.line([(X + DW / 2, ys["D4b"]), (XM - 2.1, ys["D4b"])], lw=0.9)
    lab(X + DW / 2 + 0.45, ys["D4b"] + 0.2, "да")
    c.line([(XM, ys["D4b"] - 0.45), (XM, ys["P5"] + 0.575)], lw=0.9)
    c.line([(XM - 1.8, ys["P5"]), (X + PW / 2, ys["P5"])], lw=0.9)
    lab(XM - 2.35, ys["P5"] + 0.22, "да")
    c.line([(XM + 1.8, ys["P5"]), (BUS, ys["P5"])], lw=0.9, arrow=False)
    lab(XM + 2.35, ys["P5"] + 0.22, "нет")
    # шина
    c.line([(BUS, ys["D1"]), (BUS, ys["D6"]), (XM + 2.1, ys["D6"])], lw=0.9)
    # критерии выполнены -> RESOLVED, нет гипотез -> ESCALATED
    c.line([(X + DW / 2, ys["D5"]), (XM - 2.1, ys["D5"])], lw=0.9)
    lab(X + DW / 2 + 0.45, ys["D5"] + 0.2, "да")
    c.line([(X + DW / 2, ys["D6"]), (XM - 2.1, ys["D6"])], lw=0.9)
    lab(X + DW / 2 + 0.45, ys["D6"] + 0.2, "нет")
    # цикл: следующая гипотеза
    c.line([(X - DW / 2, ys["D6"]), (0.75, ys["D6"]), (0.75, ys["P3"]), (X - PW / 2, ys["P3"])], lw=0.9)
    lab(X - DW / 2 - 0.5, ys["D6"] + 0.2, "да")
    c.text(0.75, 5.6, "следующая\nгипотеза", fs=7.8, italic=True, rot=90, bg=True)
    c.save(out)


if __name__ == "__main__":
    import sys
    build(sys.argv[1])
