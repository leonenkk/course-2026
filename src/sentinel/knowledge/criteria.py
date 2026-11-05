"""Критерии успеха инструкций: предикаты ``X``, ``not X``, ``queue_slope < N``, ``queue_len <= N``.

Грамматика закрыта: всё, что не разбирается, считается ошибкой базы знаний (проверяется при загрузке),
поэтому в рантайме неизвестный критерий не может «случайно» оказаться выполненным.
"""
from __future__ import annotations

import re

from sentinel.detector.signals import queue_slope
from sentinel.domain import SIGNALS

_CMP = re.compile(r"(queue_slope|queue_len)\s*(<=|<)\s*(-?\d+(?:\.\d+)?)")


def is_valid(crit: str) -> bool:
    crit = crit.strip()
    if _CMP.fullmatch(crit):
        return True
    name = crit[4:].strip() if crit.startswith("not ") else crit
    return name in SIGNALS


def holds(crit: str, signals: frozenset, window: list) -> bool:
    crit = crit.strip()
    m = _CMP.fullmatch(crit)
    if m:
        value = queue_slope(window) if m.group(1) == "queue_slope" else window[-1].queue_len
        limit = float(m.group(3))
        return value <= limit if m.group(2) == "<=" else value < limit
    if crit.startswith("not "):
        return crit[4:].strip() not in signals
    if crit in SIGNALS:
        return crit in signals
    raise ValueError(f"unknown success criterion: {crit!r}")
