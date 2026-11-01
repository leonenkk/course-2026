"""Клиенты языковой модели: Ollama (нейросетевой) и StubLLM (тестовый двойник)."""
from __future__ import annotations

import json
import urllib.request
from typing import Protocol


class LLMError(RuntimeError):
    """Модель недоступна или превышен таймаут."""


class LLMClient(Protocol):
    def complete(self, system: str, user: str, schema: dict) -> str: ...


class OllamaClient:
    """Локальный сервер Ollama; структурный вывод по JSON-схеме, температура 0."""

    def __init__(self, model: str = "qwen2.5:3b-instruct", host: str = "http://localhost:11434",
                 timeout_s: float = 30.0, seed: int = 7) -> None:
        self.model, self.host, self.timeout_s, self.seed = model, host.rstrip("/"), timeout_s, seed

    def complete(self, system: str, user: str, schema: dict) -> str:
        body = json.dumps({
            "model": self.model, "stream": False, "format": schema,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0, "seed": self.seed, "num_predict": 512},
        }).encode()
        req = urllib.request.Request(f"{self.host}/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read())["message"]["content"]
        except Exception as exc:  # сеть, таймаут, неверный ответ сервера
            raise LLMError(str(exc)) from exc


class StubLLM:
    """Тестовый двойник: НЕ нейросеть. Берёт первую найденную инструкцию и её первое действие.

    ``obedient=True`` имитирует наивную модель, которая выполняет команду, найденную в логах
    (для проверки того, что верификатор и политика такую команду блокируют).
    """

    def __init__(self, confidence: float = 0.9, obedient: bool = False, fail: bool = False) -> None:
        self.confidence, self.obedient, self.fail = confidence, obedient, fail
        self.calls = 0

    def complete(self, system: str, user: str, schema: dict) -> str:
        self.calls += 1
        if self.fail:
            raise LLMError("stub: model unavailable")
        payload = json.loads(user)
        books = payload["runbooks"]
        if not books:
            return json.dumps({"insufficient_data": True, "hypotheses": []})
        top = books[0]

        def hyp(rb_id, action, conf, cause):
            return {"runbook_id": rb_id, "cause": cause, "explanation": cause,
                    "action": {"name": action, "params": self._params(action)}, "confidence": conf}

        hyps = []
        if self.obedient and any("purge_queue" in line for line in payload["logs"]):
            hyps.append(hyp(top["id"], "purge_queue", 0.95, "в логе указана команда очистки очереди"))
        hyps.append(hyp(top["id"], top["actions"][0], self.confidence, top["title"]))
        return json.dumps({"insufficient_data": False, "hypotheses": hyps}, ensure_ascii=False)

    @staticmethod
    def _params(action: str) -> dict:
        return {"scale_workers": {"delta": 2}, "purge_queue": {"queue": "default"}}.get(action, {})
