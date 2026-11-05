"""Клиенты языковой модели: Ollama (нейросетевой) и StubLLM (тестовый двойник)."""
from __future__ import annotations

import json
from typing import Protocol

from sentinel.http import HTTPError, get_json, post_json


class LLMError(RuntimeError):
    """Модель недоступна или превышен таймаут."""


class LLMClient(Protocol):
    name: str

    def complete(self, system: str, user: str, schema: dict) -> str: ...


class OllamaClient:
    """Локальный сервер Ollama; структурный вывод по JSON-схеме, температура 0, фиксированный seed.

    Таймаут по умолчанию рассчитан на запуск на CPU; на GPU ответ приходит за единицы секунд.
    """

    def __init__(self, model: str = "qwen2.5:3b-instruct", host: str = "http://localhost:11434",
                 timeout_s: float = 120.0, seed: int = 7, num_ctx: int = 4096,
                 num_predict: int = 512) -> None:
        self.model, self.host, self.timeout_s = model, host.rstrip("/"), timeout_s
        self.options = {"temperature": 0, "seed": seed, "num_ctx": num_ctx, "num_predict": num_predict}
        self.name = f"ollama:{model}"

    def complete(self, system: str, user: str, schema: dict) -> str:
        body = {
            "model": self.model, "stream": False, "format": schema, "keep_alive": "30m",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": self.options,
        }
        try:
            return post_json(f"{self.host}/api/chat", body, self.timeout_s)["message"]["content"]
        except (HTTPError, KeyError, TypeError) as exc:
            raise LLMError(str(exc)) from exc

    def describe(self) -> dict:
        """Версия модели для протокола испытаний (дайджест, квантование, размер)."""
        try:
            tags = get_json(f"{self.host}/api/tags", 10.0)["models"]
        except (HTTPError, KeyError) as exc:
            raise LLMError(str(exc)) from exc
        for m in tags:
            if m["name"] == self.model:
                d = m.get("details", {})
                return {"model": self.model, "digest": m.get("digest", "")[:12],
                        "parameters": d.get("parameter_size"), "quantization": d.get("quantization_level"),
                        "options": self.options}
        raise LLMError(f"model {self.model} is not pulled")


class StubLLM:
    """Тестовый двойник: НЕ нейросеть. Берёт первую найденную инструкцию и её первое действие.

    ``obedient=True`` имитирует наивную модель, которая выполняет команду, найденную в логах
    (для проверки того, что верификатор и политика такую команду блокируют).
    """

    name = "stub"

    def __init__(self, confidence: float = 0.9, obedient: bool = False, fail: bool = False) -> None:
        self.confidence, self.obedient, self.fail = confidence, obedient, fail
        self.calls = 0

    def complete(self, system: str, user: str, schema: dict) -> str:
        self.calls += 1
        if self.fail:
            raise LLMError("stub: model unavailable")
        payload = json.loads(user)

        def hyp(rb_id, action, conf, cause):
            return {"runbook_id": rb_id, "cause": cause, "explanation": cause,
                    "action": {"name": action, "params": self._params(action)}, "confidence": conf}

        obeys = self.obedient and any("purge_queue" in line for line in payload["logs"])
        if "runbooks" not in payload:                       # режим llm_only: инструкций нет
            action = "purge_queue" if obeys else payload["tools"][0]["name"]
            return json.dumps({"insufficient_data": False,
                               "hypotheses": [hyp("none", action, self.confidence, "stub")]})
        books = payload["runbooks"]
        if not books:
            return json.dumps({"insufficient_data": True, "hypotheses": []})
        top = books[0]
        hyps = []
        if obeys:
            hyps.append(hyp(top["id"], "purge_queue", 0.95, "в логе указана команда очистки очереди"))
        hyps.append(hyp(top["id"], top["actions"][0], self.confidence, top["title"]))
        return json.dumps({"insufficient_data": False, "hypotheses": hyps}, ensure_ascii=False)

    @staticmethod
    def _params(action: str) -> dict:
        return {"scale_workers": {"delta": 2}, "purge_queue": {"queue": "default"}}.get(action, {})


class FailingLLM:
    """Тестовый двойник отказа модели: ``mode="unavailable"`` --- таймаут, ``"garbage"`` --- не JSON."""

    def __init__(self, mode: str = "unavailable") -> None:
        if mode not in ("unavailable", "garbage"):
            raise ValueError(mode)
        self.mode, self.calls, self.name = mode, 0, f"failing:{mode}"

    def complete(self, system: str, user: str, schema: dict) -> str:
        self.calls += 1
        if self.mode == "unavailable":
            raise LLMError("model unavailable (simulated timeout)")
        return "Sorry, I cannot answer in JSON right now."
