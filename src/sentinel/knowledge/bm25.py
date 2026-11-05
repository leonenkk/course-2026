"""BM25 (формула 2.2 записки) и нормализация терминов.

Русские и английские словоформы приводятся к основе стеммером Snowball (Портер); идентификаторы
сигналов и действий (``WORKERS_DOWN``, ``restart_workers``) и числа не изменяются, чтобы точное
совпадение кодов оставалось сильным признаком. Режим ``truncate`` (усечение до 6 символов) оставлен
для сравнения в экспериментах раздела 3.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

import snowballstemmer

_TOKEN = re.compile(r"\w+", re.UNICODE)
_CYRILLIC = re.compile(r"[а-я]")
_RU = snowballstemmer.stemmer("russian")
_EN = snowballstemmer.stemmer("english")

STEMMERS = ("snowball", "truncate")


@lru_cache(maxsize=65536)
def _stem(token: str) -> str:
    return _RU.stemWord(token) if _CYRILLIC.search(token) else _EN.stemWord(token)


def tokenize(text: str, stem: str = "snowball") -> list[str]:
    tokens = _TOKEN.findall(text.lower().replace("ё", "е"))
    if stem == "truncate":
        return [t if "_" in t else t[:6] for t in tokens]
    if stem != "snowball":
        raise ValueError(f"unknown stemmer: {stem}")
    return [t if "_" in t or t.isdigit() else _stem(t) for t in tokens]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75, stem: str = "snowball") -> None:
        self.k1, self.b, self.stem = k1, b, stem
        self.tf = [Counter(tokenize(d, stem)) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avgdl = sum(self.len) / max(len(docs), 1)
        df: Counter = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def score(self, query: str, i: int) -> float:
        return self._score(set(tokenize(query, self.stem)), i)

    def scores(self, query: str, docs: list[int]) -> list[float]:
        terms = set(tokenize(query, self.stem))            # запрос разбирается один раз
        return [self._score(terms, i) for i in docs]

    def _score(self, terms: set[str], i: int) -> float:
        tf, dl = self.tf[i], self.len[i]
        total = 0.0
        for t in terms:
            f = tf.get(t, 0)
            if f:
                total += self.idf[t] * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return total
