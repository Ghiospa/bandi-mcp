"""Il log d'uso: cosa registra, cosa non deve registrare, e che non rompe mai una chiamata."""

import asyncio
import sqlite3

from bandi_mcp import uso


def test_conteggi_da_cerca_bandi():
    contenuto = {
        "compatibili": [{"bando_id": "a"}, {"bando_id": "b"}],
        "dati_che_migliorerebbero_la_ricerca": [{"campo": "eta_titolare"}],
    }
    assert uso._conteggi(contenuto) == (1, 2)


def test_conteggi_da_verifica_ammissibilita():
    contenuto = {"esito": {"campi_mancanti": ["ateco", "addetti_ula"]}, "bando": {}}
    assert uso._conteggi(contenuto) == (2, 1)


def test_conteggi_su_forma_sconosciuta_non_indovina():
    assert uso._conteggi({"qualcosa": 1}) == (None, None)
    assert uso._conteggi(None) == (None, None)


def test_tool_error_registrato_come_errore():
    assert uso._esito_e_contenuto({"content": [], "isError": True}) == ("errore", None)
    esito, contenuto = uso._esito_e_contenuto({"content": [], "isError": False, "structuredContent": {"a": 1}})
    assert (esito, contenuto) == ("ok", {"a": 1})


def test_scrive_su_sqlite_e_non_registra_il_profilo(tmp_path, monkeypatch, capsys):
    db = tmp_path / "uso.sqlite3"
    monkeypatch.setenv("BANDI_LOG_DB", str(db))
    uso.registra("cerca_bandi", "ok", 12, campi_mancanti=3, bandi_restituiti=5)
    righe = list(sqlite3.connect(db).execute("SELECT tool, esito, durata_ms, campi_mancanti, bandi_restituiti FROM chiamate"))
    assert righe == [("cerca_bandi", "ok", 12, 3, 5)]
    colonne = [r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(chiamate)")]
    for vietata in ("profilo", "ragione_sociale", "partita_iva", "ateco", "ip"):
        assert vietata not in colonne, f"il log non deve avere una colonna '{vietata}'"


def test_un_log_rotto_non_fa_fallire_la_chiamata(monkeypatch):
    # /dev/null è un file: creare una cartella dentro fallisce
    monkeypatch.setenv("BANDI_LOG_DB", "/dev/null/non/scrivibile/uso.sqlite3")
    uso.registra("cerca_bandi", "ok", 1)  # non deve sollevare


def test_middleware_registra_e_restituisce_il_risultato(monkeypatch, tmp_path):
    monkeypatch.setenv("BANDI_LOG_DB", str(tmp_path / "uso.sqlite3"))
    risultato = {"content": [], "isError": False, "structuredContent": {"compatibili": [{"x": 1}]}}

    class Ctx:
        method = "tools/call"
        params = {"name": "cerca_bandi"}

    async def call_next(ctx):
        return risultato

    assert asyncio.run(uso.middleware_uso(Ctx(), call_next)) is risultato
    righe = list(sqlite3.connect(tmp_path / "uso.sqlite3").execute("SELECT tool, esito, bandi_restituiti FROM chiamate"))
    assert righe == [("cerca_bandi", "ok", 1)]
