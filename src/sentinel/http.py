"""Минимальный JSON-клиент поверх стандартной библиотеки (без внешних зависимостей)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class HTTPError(RuntimeError):
    """Сетевая ошибка, таймаут или неожиданный ответ сервера."""


def post_json(url: str, body: dict, timeout_s: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise HTTPError(f"{url}: {exc}") from exc


def get_json(url: str, timeout_s: float) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise HTTPError(f"{url}: {exc}") from exc
