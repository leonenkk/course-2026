"""Реестр допустимых действий: класс риска, схема и лимиты параметров (проверки V3, V5, правило P1)."""
from __future__ import annotations

from dataclasses import dataclass, field

from sentinel.domain import Risk


@dataclass(frozen=True)
class ActionSpec:
    name: str
    risk: Risk
    timeout_s: float = 30.0
    int_limits: dict = field(default_factory=dict)       # параметр -> (min, max)
    allowed_values: dict = field(default_factory=dict)   # параметр -> допустимые значения
    description: str = ""
    params_hint: dict = field(default_factory=dict)      # пример параметров для запроса к модели

    def describe(self) -> dict:
        """Описание инструмента для языковой модели (без класса риска: решение о риске --- не её)."""
        return {"name": self.name, "description": self.description, "params": self.params_hint}


class ActionRegistry:
    def __init__(self, specs: list[ActionSpec]) -> None:
        self._specs = {s.name: s for s in specs}

    def __contains__(self, name: str) -> bool:
        return name in self._specs

    def get(self, name: str) -> ActionSpec:
        return self._specs[name]

    def names(self) -> list[str]:
        return list(self._specs)

    def validate(self, name: str, params: dict) -> str | None:
        """Возвращает текст нарушения или None, если действие и параметры допустимы."""
        spec = self._specs.get(name)
        if spec is None:
            return f"action {name!r} is not in the registry"
        for key, (lo, hi) in spec.int_limits.items():
            if key in params and not (isinstance(params[key], int) and lo <= params[key] <= hi):
                return f"param {key!r} must be an integer in [{lo}, {hi}]"
        for key, allowed in spec.allowed_values.items():
            if key in params and params[key] not in allowed:
                return f"param {key!r} must be one of {sorted(allowed)}"
        unknown = set(params) - {"delta", "queue", "title", "body", "message"}
        return f"unknown params {sorted(unknown)}" if unknown else None


def default_registry() -> ActionRegistry:
    return ActionRegistry([
        ActionSpec("restart_workers", Risk.LOW, description="перезапустить процессы воркеров"),
        ActionSpec("scale_workers", Risk.MEDIUM, int_limits={"delta": (1, 4)},
                   description="добавить воркеры (delta --- целое от 1 до 4)", params_hint={"delta": 2}),
        ActionSpec("purge_queue", Risk.HIGH, allowed_values={"queue": {"default"}},
                   description="удалить все сообщения из очереди", params_hint={"queue": "default"}),
        ActionSpec("create_ticket", Risk.LOW, description="создать тикет для разбора людьми",
                   params_hint={"title": "...", "body": "..."}),
        ActionSpec("notify_oncall", Risk.LOW, description="уведомить дежурного инженера",
                   params_hint={"message": "..."}),
    ])
