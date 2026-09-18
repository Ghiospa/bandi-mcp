"""
Log anonimo delle chiamate ai tool.

Serve a misurare l'uso reale — quante chiamate, a quali tool, con che esito, quanto
spesso all'agente mancano dati — senza tenere niente di identificabile.

**Non viene registrato nulla del profilo**: né ragione sociale, né P.IVA, né ATECO,
né importi. Solo il nome del tool, il momento, l'esito, la durata e due conteggi
(campi mancanti, bandi restituiti). Se cambi questo file, questa riga è il vincolo.

Due destinazioni, entrambe opzionali e non bloccanti:
- SQLite in `BANDI_LOG_DB` (default `data/uso.sqlite3`), per `scripts/report_uso.py`
- una riga JSON su stdout, che le piattaforme di hosting conservano nei log anche
  quando il filesystem è effimero
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_LOCK = threading.Lock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS chiamate (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               TEXT    NOT NULL,
    tool             TEXT    NOT NULL,
    esito            TEXT    NOT NULL,
    durata_ms        INTEGER,
    campi_mancanti   INTEGER,
    bandi_restituiti INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chiamate_ts ON chiamate(ts);
"""


def percorso_db() -> Optional[Path]:
    """None disattiva la scrittura su SQLite (BANDI_LOG_DB vuoto)."""
    valore = os.environ.get("BANDI_LOG_DB", "data/uso.sqlite3")
    return Path(valore) if valore else None


def _connessione(percorso: Path) -> sqlite3.Connection:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(percorso, timeout=5)
    conn.executescript(_SCHEMA)
    return conn


def registra(
    tool: str,
    esito: str,
    durata_ms: int,
    campi_mancanti: Optional[int] = None,
    bandi_restituiti: Optional[int] = None,
) -> None:
    """Non solleva mai: un log rotto non deve far fallire una chiamata dell'agente."""
    riga = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": tool,
        "esito": esito,
        "durata_ms": durata_ms,
        "campi_mancanti": campi_mancanti,
        "bandi_restituiti": bandi_restituiti,
    }
    try:
        print(json.dumps({"uso": riga}, ensure_ascii=False), file=sys.stdout, flush=True)
    except Exception:
        pass

    try:
        percorso = percorso_db()
        if percorso is None:
            return
        with _LOCK:
            conn = _connessione(percorso)
            try:
                conn.execute(
                    "INSERT INTO chiamate (ts, tool, esito, durata_ms, campi_mancanti, bandi_restituiti)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (riga["ts"], tool, esito, durata_ms, campi_mancanti, bandi_restituiti),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Estrazione dei due conteggi dal risultato
# --------------------------------------------------------------------------- #
def _conteggi(contenuto: Any) -> tuple[Optional[int], Optional[int]]:
    """
    Quanti campi mancano all'agente e quanti bandi gli sono tornati, letti dallo
    `structuredContent` della risposta. Conosce le forme dei nostri tool; su qualsiasi
    altra cosa restituisce (None, None) invece di indovinare.
    """
    if not isinstance(contenuto, dict):
        return None, None

    # verifica_ammissibilita -> {"esito": {...}, "bando": {...}}
    esito = contenuto.get("esito")
    if isinstance(esito, dict) and isinstance(esito.get("campi_mancanti"), list):
        return len(esito["campi_mancanti"]), 1

    # cerca_bandi -> {"compatibili": [...], "dati_che_migliorerebbero_la_ricerca": [...]}
    compatibili = contenuto.get("compatibili")
    if isinstance(compatibili, list):
        da_chiedere = contenuto.get("dati_che_migliorerebbero_la_ricerca")
        n_campi = len(da_chiedere) if isinstance(da_chiedere, list) else None
        return n_campi, len(compatibili)

    return None, None


def _esito_e_contenuto(risultato: Any) -> tuple[str, Any]:
    """
    Il middleware riceve il risultato di `tools/call` già formato:
    `{"content": [...], "isError": bool, "structuredContent": {...}}`.
    Un ToolError non risale come eccezione, arriva qui con isError=True.
    """
    if hasattr(risultato, "model_dump"):
        risultato = risultato.model_dump(by_alias=True)
    if not isinstance(risultato, dict):
        return "ok", None
    esito = "errore" if risultato.get("isError") else "ok"
    return esito, risultato.get("structuredContent")


# --------------------------------------------------------------------------- #
# Middleware MCP
# --------------------------------------------------------------------------- #
async def middleware_uso(ctx: Any, call_next: Any) -> Any:
    """
    Osserva ogni `tools/call` e ne registra l'esito. Registra anche gli errori:
    un tool che fallisce spesso è il segnale più utile che abbiamo.
    """
    if ctx.method != "tools/call":
        return await call_next(ctx)

    params = ctx.params if isinstance(ctx.params, dict) else {}
    tool = str(params.get("name", "sconosciuto"))
    inizio = time.perf_counter()
    try:
        risultato = await call_next(ctx)
    except Exception:
        registra(tool, "errore", int((time.perf_counter() - inizio) * 1000))
        raise
    esito, contenuto = _esito_e_contenuto(risultato)
    campi, bandi = _conteggi(contenuto)
    registra(tool, esito, int((time.perf_counter() - inizio) * 1000), campi, bandi)
    return risultato
