"""Runbook-инструкции: Markdown с YAML-заголовком (формат --- листинг 2.1 записки)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Runbook:
    id: str
    title: str
    service: str
    signals_required: tuple
    signals_excluded: tuple
    actions: tuple
    success_criteria: tuple
    body: str
    symptoms: tuple = field(default=())

    @property
    def text(self) -> str:
        """Текст для индексации: заголовок, идентификаторы сигналов и тело."""
        return " ".join([self.title, " ".join(self.signals_required), self.body])


def parse_runbook(raw: str) -> Runbook:
    if not raw.startswith("---"):
        raise ValueError("runbook must start with a YAML front matter")
    _, header, body = raw.split("---", 2)
    meta = yaml.safe_load(header)
    return Runbook(
        id=meta["id"], title=meta["title"], service=meta["service"],
        signals_required=tuple(meta.get("signals_required", ())),
        signals_excluded=tuple(meta.get("signals_excluded", ())),
        actions=tuple(meta.get("actions", ())),
        success_criteria=tuple(meta.get("success_criteria", ())),
        body=body.strip(),
    )


def load_runbooks(directory: str | Path) -> list[Runbook]:
    return [parse_runbook(p.read_text(encoding="utf-8")) for p in sorted(Path(directory).glob("RB-*.md"))]
