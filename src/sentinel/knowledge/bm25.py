"""BM25 (формула 2.2 записки) с грубой префиксной нормализацией русских словоформ."""
from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    # усечение до 6 символов --- примитивная замена стеммера; идентификаторы (WORKERS_DOWN) не трогаем
    return [t if "_" in t else t[:6] for t in _TOKEN.findall(text.lower())]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tf = [Counter(tokenize(d)) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avgdl = sum(self.len) / max(len(docs), 1)
        df: Counter = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def score(self, query: str, i: int) -> float:
        tf, dl = self.tf[i], self.len[i]
        total = 0.0
        for t in set(tokenize(query)):
            f = tf.get(t, 0)
            if f:
                total += self.idf[t] * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return total
