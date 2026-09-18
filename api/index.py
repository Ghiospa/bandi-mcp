"""
Punto d'ingresso per il deploy serverless su Vercel.

Vercel esegue ogni richiesta in una lambda che può essere nuova: niente sessioni MCP
condivise, niente streaming SSE, filesystem effimero. I default qui sotto adattano
l'app a quel modello senza cambiare il comportamento su un processo normale, dove
gli stessi interruttori restano spenti (vedi bandi_mcp/http_app.py).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# MCP senza stato e senza SSE: obbligatorio su serverless.
os.environ.setdefault("BANDI_STATELESS", "1")
os.environ.setdefault("BANDI_JSON_RESPONSE", "1")
# Il filesystem non sopravvive alla richiesta: il log d'uso resta solo su stdout,
# che Vercel conserva nei log della funzione.
os.environ.setdefault("BANDI_LOG_DB", "")
# Il limite per IP è in memoria, quindi vale per istanza e non globalmente: è una
# protezione parziale contro un singolo client in loop, non contro un attacco.
os.environ.setdefault("BANDI_RATE_LIMIT", "60")

if not os.environ.get("BANDI_BASE_URL"):
    dominio = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or os.environ.get("VERCEL_URL")
    if dominio:
        os.environ["BANDI_BASE_URL"] = f"https://{dominio}"

from bandi_mcp.http_app import crea_app  # noqa: E402

app = crea_app()
