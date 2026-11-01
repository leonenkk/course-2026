from _draw import Canvas, WHITE, SYM, EXT


def build(out):
    c = Canvas(16.5, 11.2)
    # граница системы
    c.rect(3.7, 0.5, 13.0, 10.7, style=dict(fc="#fbfbfb", ec="#333333"), ls="--", z=0)
    c.text(8.35, 10.35, "Гибридная система Sentinel", fs=10, bold=True, bg=False)

    # Варианты использования
    L, R = 6.5, 11.3
    W, H = 4.2, 1.05
    u7 = (L, 9.0, "Управлять базой знаний\nи политиками")
    u8 = (L, 7.2, "Найти инструкции\nв базе знаний")
    u4 = (L, 5.4, "Подтвердить или\nотклонить действие")
    u5 = (L, 3.6, "Эскалировать\nинцидент")
    u6 = (L, 1.8, "Просмотреть инцидент,\nаудит и отчёт")
    u1 = (R, 9.0, "Обнаружить\nинцидент")
    u2 = (R, 7.2, "Диагностировать\nпричину")
    u3 = (R, 5.4, "Выбрать и выполнить\nдействие")
    u9 = (R, 3.6, "Проверить результат\nдействия")
    for x, y, t in (u7, u8, u4, u5, u6, u1, u2, u3, u9):
        c.ellipse(x, y, W, H, t, fs=8.8)

    # include / extend
    c.line([(R - W / 2, 7.2), (L + W / 2, 7.2)], ls="--", lw=0.9)
    c.text((L + R) / 2, 7.45, "«include»", fs=8, italic=True)
    c.line([(R, 5.4 - H / 2), (R, 3.6 + H / 2)], ls="--", lw=0.9)
    c.text(R + 1.0, 4.5, "«include»", fs=8, italic=True)
    c.line([(L + W / 2, 5.4), (R - W / 2, 5.4)], ls="--", lw=0.9)
    c.text((L + R) / 2, 5.65, "«extend»", fs=8, italic=True)
    c.line([(L + W / 2 - 0.2, 3.85), (R - W / 2 + 0.55, 4.95)], ls="--", lw=0.9)
    c.text(8.85, 4.0, "«extend»", fs=8, italic=True)

    # Актёры
    c.actor(1.7, 8.9, "Разработчик\n(владелец БЗ\nи политик)")
    c.actor(1.7, 3.6, "Дежурный\nинженер")
    c.box(15.15, 8.2, 2.5, 1.1, "Сервер языковой\nмодели", style=EXT, fs=8.8)
    c.box(15.15, 4.6, 2.5, 1.1, "Демо-сервис", style=EXT, fs=8.8)
    c.text(15.15, 8.95, "«система»", fs=7.5, italic=True, bg=False)
    c.text(15.15, 5.35, "«система»", fs=7.5, italic=True, bg=False)

    # связи актёров
    c.line([(1.7 + 0.45, 8.95), (L - W / 2 + 0.25, 9.0 - 0.1)], arrow=False)
    for y in (5.4, 3.6, 1.8):
        c.line([(1.7 + 0.45, 3.7), (L - W / 2 + 0.05, y)], arrow=False)
    c.line([(15.15 - 1.25, 8.2), (R + W / 2 - 0.1, 7.5)], arrow=False)
    for y in (9.0, 5.4, 3.6):
        c.line([(15.15 - 1.25, 4.7), (R + W / 2 - 0.05, y)], arrow=False)
    c.save(out)


if __name__ == "__main__":
    import sys
    build(sys.argv[1])
