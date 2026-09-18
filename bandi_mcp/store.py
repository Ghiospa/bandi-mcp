"""Caricamento del catalogo bandi da JSON. Un file per territorio, per ora solo la Sicilia."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from .schema import Bando

DATA_DIR = Path(os.environ.get("BANDI_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))


@lru_cache(maxsize=1)
def carica_catalogo() -> list[Bando]:
    bandi: list[Bando] = []
    for path in sorted(DATA_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
        items = raw["bandi"] if isinstance(raw, dict) else raw
        for item in items:
            bandi.append(Bando.model_validate(item))
    ids = [b.id for b in bandi]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"ID bando duplicati nel catalogo: {sorted(dup)}")
    return bandi


def trova_bando(bando_id: str) -> Bando | None:
    for b in carica_catalogo():
        if b.id == bando_id:
            return b
    return None


def ricarica() -> int:
    carica_catalogo.cache_clear()
    return len(carica_catalogo())
