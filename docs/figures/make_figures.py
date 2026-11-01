"""Генерация всех рисунков раздела 2 пояснительной записки.

Запуск:  python make_figures.py <каталог для PNG>
Требуется только matplotlib и шрифт Liberation Serif.
"""
import sys
from pathlib import Path

import fig_architecture
import fig_er
import fig_flow
import fig_sequence
import fig_states
import fig_usecases

FIGURES = {
    "fig_usecases.png": fig_usecases,
    "fig_architecture.png": fig_architecture,
    "fig_sequence.png": fig_sequence,
    "fig_states.png": fig_states,
    "fig_er.png": fig_er,
    "fig_flow.png": fig_flow,
}

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    for name, module in FIGURES.items():
        module.build(str(out / name))
        print("OK", name)
