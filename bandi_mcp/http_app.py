"""
Assemblaggio dell'app HTTP per il deploy pubblico.

Il server MCP resta quello di `server.py`: qui intorno ci mettiamo solo ciò che
serve a stare in piedi su internet senza autenticazione —

- protezione DNS rebinding con gli host ammessi presi dall'ambiente
- limite di richieste per IP, perché l'endpoint è aperto
- `/health`, che dice anche quanto è vecchio il catalogo

Configurazione via ambiente (tutto opzionale, default adatti allo sviluppo locale):

    PORT                 porta di ascolto (default 8000; le piattaforme la impongono)
    BANDI_HOST           indirizzo di bind (default 127.0.0.1; in container 0.0.0.0)
    BANDI_ALLOWED_HOSTS  host ammessi, separati da virgola, es. "bandi.prodgai.com"
                         se vuoto la protezione DNS rebinding resta disattivata
    BANDI_RATE_LIMIT     richieste al minuto per IP (default 60, 0 disattiva)
    BANDI_TRUST_PROXY    "0" per NON fidarsi di X-Forwarded-For (default: fidarsi)
    BANDI_LOG_DB         percorso SQLite del log d'uso (vedi uso.py)
    BANDI_BASE_URL       URL pubblico, per canonical e sitemap (default bandi.prodgai.com)
    BANDI_SITO           "0" per non servire le pagine HTML generate dal catalogo
    BANDI_SITO_DIR       dove generarle (default: cartella temporanea, rifatta a ogni avvio)

Avvio: `python -m bandi_mcp.server --http`, oppure
`uvicorn --factory bandi_mcp.http_app:crea_app --host 0.0.0.0 --port $PORT`.
"""

from __future__ import annotations

import os
import tempfile
import time
from collections import deque
from datetime import date
from pathlib import Path
from typing import Deque

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.transport_security import TransportSecuritySettings

from .server import server
from .sito import genera
from .store import carica_catalogo


def _lista_env(nome: str) -> list[str]:
    return [v.strip() for v in os.environ.get(nome, "").split(",") if v.strip()]


def _sicurezza_trasporto() -> TransportSecuritySettings | None:
    """None = il default della libreria, che disattiva la protezione (sviluppo locale)."""
    host_ammessi = _lista_env("BANDI_ALLOWED_HOSTS")
    if not host_ammessi:
        return None
    origini = _lista_env("BANDI_ALLOWED_ORIGINS") or [f"https://{h}" for h in host_ammessi]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=host_ammessi + [f"{h}:*" for h in host_ammessi],
        allowed_origins=origini,
    )


class LimiteRichieste:
    """
    Finestra scorrevole di un minuto per IP. In memoria: basta finché l'istanza è una,
    e quando non lo sarà più il limite andrà spostato davanti (proxy o gateway).
    Non protegge da un attacco distribuito: serve a impedire che un singolo client
    in loop consumi il servizio per tutti.
    """

    def __init__(self, app: ASGIApp, al_minuto: int, fidati_del_proxy: bool = True) -> None:
        self.app = app
        self.al_minuto = al_minuto
        self.fidati_del_proxy = fidati_del_proxy
        self._finestre: dict[str, Deque[float]] = {}

    def _ip(self, scope: Scope) -> str:
        if self.fidati_del_proxy:
            for nome, valore in scope.get("headers", []):
                if nome == b"x-forwarded-for":
                    return valore.decode("latin-1").split(",")[0].strip()
        client = scope.get("client")
        return client[0] if client else "sconosciuto"

    def _superato(self, ip: str) -> bool:
        adesso = time.monotonic()
        finestra = self._finestre.setdefault(ip, deque())
        while finestra and adesso - finestra[0] > 60:
            finestra.popleft()
        if len(finestra) >= self.al_minuto:
            return True
        finestra.append(adesso)
        if len(self._finestre) > 10_000:  # non cresciamo all'infinito
            for chiave in [k for k, v in self._finestre.items() if not v]:
                del self._finestre[chiave]
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.al_minuto <= 0:
            await self.app(scope, receive, send)
            return
        if scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return
        if self._superato(self._ip(scope)):
            risposta = JSONResponse(
                {
                    "errore": "troppe richieste",
                    "limite_al_minuto": self.al_minuto,
                    "cosa_fare": "riprova tra un minuto, oppure installa il server in locale (vedi README) per non avere limiti",
                },
                status_code=429,
                headers={"Retry-After": "60"},
            )
            await risposta(scope, receive, send)
            return
        await self.app(scope, receive, send)


@server.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    """Stato del servizio e freschezza del dato: un catalogo vecchio è un servizio rotto."""
    bandi = carica_catalogo()
    controlli = [b.ultimo_controllo for b in bandi]
    piu_vecchio = min(controlli) if controlli else None
    return JSONResponse(
        {
            "stato": "ok",
            "bandi": len(bandi),
            "aperti": sum(1 for b in bandi if b.stato in ("aperto", "sportello_continuo")),
            "controllo_piu_vecchio": piu_vecchio.isoformat() if piu_vecchio else None,
            "giorni_dall_ultimo_controllo": (date.today() - piu_vecchio).days if piu_vecchio else None,
            "endpoint_mcp": "/mcp",
        }
    )


def _monta_sito(app: Starlette) -> None:
    """
    Le pagine si rigenerano dal catalogo a ogni avvio: non possono divergere dal motore.
    Il mount va in coda alle rotte, dopo /mcp e /health, che restano prioritarie.
    """
    cartella = Path(os.environ.get("BANDI_SITO_DIR") or tempfile.mkdtemp(prefix="bandi-sito-"))
    genera(cartella)
    app.routes.append(Mount("/", app=StaticFiles(directory=cartella, html=True), name="sito"))


def crea_app() -> Starlette:
    app = server.streamable_http_app(transport_security=_sicurezza_trasporto())
    al_minuto = int(os.environ.get("BANDI_RATE_LIMIT", "60"))
    fidati = os.environ.get("BANDI_TRUST_PROXY", "1") != "0"
    app.add_middleware(LimiteRichieste, al_minuto=al_minuto, fidati_del_proxy=fidati)
    if os.environ.get("BANDI_SITO", "1") != "0":
        _monta_sito(app)
    return app


def avvia() -> None:
    import uvicorn

    uvicorn.run(
        crea_app(),
        host=os.environ.get("BANDI_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        log_level=os.environ.get("BANDI_LOG_LEVEL", "info"),
        forwarded_allow_ips="*" if os.environ.get("BANDI_TRUST_PROXY", "1") != "0" else None,
    )
