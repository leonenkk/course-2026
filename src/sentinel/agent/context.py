"""Сборщик контекста: единый формат, очистка недоверенного текста логов."""
from __future__ import annotations

import re

from sentinel.config import Settings
from sentinel.domain import LOG_INJECTION_SUSPECT, Incident, IncidentContext, LogLine, Sample

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def sanitize_line(text: str, limit: int) -> str:
    return _CONTROL.sub("", text)[:limit]


def build_context(incident: Incident, samples: list[Sample], logs: list[LogLine], signals: frozenset,
                  cfg: Settings | None = None, max_lines: int = 20) -> IncidentContext:
    cfg = cfg or Settings()
    unique: list[str] = []
    for line in reversed(logs):
        text = sanitize_line(f"{line.level}: {line.text}", cfg.log_line_limit)
        if text not in unique:
            unique.append(text)
        if len(unique) >= max_lines:
            break
    return IncidentContext(incident, list(samples), list(reversed(unique)), signals,
                           injection_suspect=LOG_INJECTION_SUSPECT in signals)
