"""Эмбеддинги.

HashingEmbedder --- детерминированная замена без модели: хэширование символьных триграмм.
Это НЕ нейросетевой компонент; он нужен для офлайн-тестов. Нейросетевой вариант
(BGE-M3 / multilingual-e5) подключается через SentenceTransformerEmbedder.
"""
from __future__ import annotations

import zlib
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
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
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1.0, norms)


class SentenceTransformerEmbedder:
    """Нейросетевые эмбеддинги (extra ``neural``): по умолчанию BAAI/bge-m3."""

    def __init__(self, model: str = "BAAI/bge-m3") -> None:
        from sentence_transformers import SentenceTransformer  # импорт отложен

        self.model = SentenceTransformer(model)

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.model.encode(texts, normalize_embeddings=True), dtype=np.float32)
