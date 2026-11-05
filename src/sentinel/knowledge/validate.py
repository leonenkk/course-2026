"""Проверка целостности базы знаний (тестирование БЗ, раздел 3 записки).

Инструкция ссылается на словари сигналов и действий; любая ссылка вне словаря делает её
несогласованной с остальными компонентами, поэтому такая база не загружается.
"""
from __future__ import annotations

import re

from sentinel.domain import SIGNALS
from sentinel.knowledge.criteria import is_valid
from sentinel.knowledge.runbook import Runbook
from sentinel.tools.registry import ActionRegistry

_ID = re.compile(r"RB-\d{3}")


class KnowledgeBaseError(ValueError):
    pass


def problems(runbooks: list[Runbook], registry: ActionRegistry) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for rb in runbooks:
        where = rb.id or "<без id>"
        if not _ID.fullmatch(rb.id):
            out.append(f"{where}: идентификатор не соответствует шаблону RB-NNN")
        if rb.id in seen:
            out.append(f"{where}: повторяющийся идентификатор")
        seen.add(rb.id)
        if not rb.title.strip() or not rb.body.strip() or not rb.service.strip():
            out.append(f"{where}: пустой заголовок, сервис или текст")
        if not rb.signals_required:
            out.append(f"{where}: не заданы обязательные сигналы")
        for s in set(rb.signals_required) | set(rb.signals_excluded):
            if s not in SIGNALS:
                out.append(f"{where}: неизвестный сигнал {s}")
        if set(rb.signals_required) & set(rb.signals_excluded):
            out.append(f"{where}: сигнал одновременно обязателен и исключён")
        if not rb.actions:
            out.append(f"{where}: пустой перечень действий")
        for a in rb.actions:
            if a not in registry:
                out.append(f"{where}: действие {a} отсутствует в реестре")
        for c in rb.success_criteria:
            if not is_valid(c):
                out.append(f"{where}: нераспознанный критерий успеха {c!r}")
    return out


def ensure_valid(runbooks: list[Runbook], registry: ActionRegistry) -> list[Runbook]:
    found = problems(runbooks, registry)
    if found:
        raise KnowledgeBaseError("; ".join(found))
    return runbooks
