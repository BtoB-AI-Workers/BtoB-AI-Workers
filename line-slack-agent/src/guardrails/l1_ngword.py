"""Layer1 NGワード照合。全角/半角正規化して部分一致で検出。"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import yaml


@dataclass(frozen=True)
class NGHit:
    category: str
    word: str
    position: int


@dataclass(frozen=True)
class NGResult:
    ok: bool
    hits: list[NGHit] = field(default_factory=list)


def _normalize(s: str) -> str:
    return unicodedata.normalize("NFKC", s).lower()


def load_ng_words(yaml_path: str | Path) -> Mapping[str, list[str]]:
    data = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    return {
        cat: (entry.get("words") or [])
        for cat, entry in (data.get("categories") or {}).items()
    }


def check(text: str, ng_words: Mapping[str, list[str]]) -> NGResult:
    normalized = _normalize(text)
    hits: list[NGHit] = []
    for category, words in ng_words.items():
        for word in words:
            if not word:
                continue
            nw = _normalize(word)
            idx = normalized.find(nw)
            if idx >= 0:
                hits.append(NGHit(category=category, word=word, position=idx))
    return NGResult(ok=not hits, hits=hits)
