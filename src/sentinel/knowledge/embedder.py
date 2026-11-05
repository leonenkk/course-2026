"""Эмбеддинги текстов.

- ``OllamaEmbedder`` --- нейросетевой компонент: модель BGE-M3 (многоязычная, d = 1024), запущенная
  локально в Ollama. Используется в экспериментах и при работе с реальной моделью.
- ``SentenceTransformerEmbedder`` --- та же модель через sentence-transformers (extra ``neural``).
- ``HashingEmbedder`` --- детерминированная замена **без нейросети** (хэширование символьных триграмм)
  для офлайн-тестов; её результаты не выдаются за результаты нейросетевого компонента.
"""
from __future__ import annotations

import zlib
from typing import Protocol

import numpy as np

from sentinel.http import HTTPError, post_json


class EmbeddingError(RuntimeError):
    """Сервис эмбеддингов недоступен или вернул некорректный ответ."""


class Embedder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> np.ndarray: ...


def _normalize(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    return (x / np.where(norms == 0, 1.0, norms)).astype(np.float32)


class HashingEmbedder:
    name = "hashing-trigram-512"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in text.lower().split():
                padded = f" {word} "
                for i in range(len(padded) - 2):
                    h = zlib.crc32(padded[i:i + 3].encode())
                    out[row, h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
        return _normalize(out)


class OllamaEmbedder:
    """Эмбеддинги через ``POST /api/embed`` локального сервера Ollama."""

    def __init__(self, model: str = "bge-m3", host: str = "http://localhost:11434",
                 timeout_s: float = 60.0, batch: int = 16) -> None:
        self.model, self.host, self.timeout_s, self.batch = model, host.rstrip("/"), timeout_s, batch
        self.name = f"ollama:{model}"

    def encode(self, texts: list[str]) -> np.ndarray:
        rows: list[list[float]] = []
        for start in range(0, len(texts), self.batch):
            chunk = texts[start:start + self.batch]
            try:
                data = post_json(f"{self.host}/api/embed", {"model": self.model, "input": chunk},
                                 self.timeout_s)
                vectors = data["embeddings"]
            except (HTTPError, KeyError, TypeError) as exc:
                raise EmbeddingError(str(exc)) from exc
            if len(vectors) != len(chunk):
                raise EmbeddingError(f"expected {len(chunk)} vectors, got {len(vectors)}")
            rows.extend(vectors)
        return _normalize(np.asarray(rows, dtype=np.float32).reshape(len(texts), -1))


class SentenceTransformerEmbedder:
    """Нейросетевые эмбеддинги через sentence-transformers (extra ``neural``)."""

    def __init__(self, model: str = "BAAI/bge-m3") -> None:
        from sentence_transformers import SentenceTransformer  # импорт отложен: тяжёлая зависимость

        self.model = SentenceTransformer(model)
        self.name = f"st:{model}"

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.model.encode(texts, normalize_embeddings=True), dtype=np.float32)
