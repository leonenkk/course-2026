"""Стенд оценки качества (раздел 3 записки): поиск инструкций, сквозные сценарии, производительность.

Результаты сохраняются в JSON (``docs/results``), из них строятся таблицы и графики записки.
"""
from __future__ import annotations

import json
import platform
import statistics
from datetime import UTC, datetime
from pathlib import Path


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[round(q) - 1]


def environment() -> dict:
    import numpy
    import sklearn

    return {"python": platform.python_version(), "platform": platform.platform(),
            "processor": platform.processor() or platform.machine(),
            "numpy": numpy.__version__, "scikit-learn": sklearn.__version__,
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds")}


def save(result: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
