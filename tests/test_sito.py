"""
Il sito generato dal catalogo: che ci sia tutto, che non menta, e che non rubi
le rotte al server MCP.
"""

import json
import os

from starlette.testclient import TestClient

from bandi_mcp import sito
from bandi_mcp.store import carica_catalogo


def test_genera_una_pagina_per_bando_piu_gli_indici(tmp_path):
    bandi = carica_catalogo()
    n = sito.genera(tmp_path)
    assert n == len(bandi) + 5  # index, llms.txt, sitemap.xml, robots.txt, catalogo.json
    for b in bandi:
        assert (tmp_path / "bandi" / f"{b.id}.html").exists(), f"manca la pagina di {b.id}"


def test_ogni_scheda_dichiara_fonte_affidabilita_e_data(tmp_path):
    sito.genera(tmp_path)
    b = carica_catalogo()[0]
    pagina = (tmp_path / "bandi" / f"{b.id}.html").read_text(encoding="utf-8")
    assert b.ultimo_controllo.strftime("%d/%m/%Y") in pagina
    assert "Affidabilità" in pagina
    assert b.fonti[0].url in pagina
    assert "/mcp" in pagina, "una scheda deve dire dove sta l'endpoint MCP"


def test_il_testo_del_catalogo_viene_sempre_scappato(tmp_path, monkeypatch):
    """Il catalogo è dato: se un domani una nota contiene HTML, non deve finire nel DOM."""
    bandi = carica_catalogo()
    velenoso = bandi[0].model_copy(update={"note": ['<script>alert("xss")</script>']})
    monkeypatch.setattr(sito, "carica_catalogo", lambda: [velenoso])
    sito.genera(tmp_path)
    pagina = (tmp_path / "bandi" / f"{velenoso.id}.html").read_text(encoding="utf-8")
    assert "<script>alert" not in pagina
    assert "&lt;script&gt;" in pagina


def test_llms_txt_manda_all_endpoint_invece_che_alle_pagine(tmp_path):
    sito.genera(tmp_path)
    testo = (tmp_path / "llms.txt").read_text(encoding="utf-8")
    assert f"{sito.BASE_URL}/mcp" in testo
    assert "cerca_bandi" in testo
    for b in carica_catalogo():
        assert b.id in testo


def test_sitemap_e_robots(tmp_path):
    sito.genera(tmp_path)
    mappa = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    for b in carica_catalogo():
        assert f"/bandi/{b.id}.html" in mappa
    robots = (tmp_path / "robots.txt").read_text(encoding="utf-8")
    assert "Sitemap:" in robots and "Disallow: /mcp" in robots


def test_catalogo_json_e_lo_stesso_dato_del_motore(tmp_path):
    sito.genera(tmp_path)
    pubblicato = json.loads((tmp_path / "catalogo.json").read_text(encoding="utf-8"))
    assert {b["id"] for b in pubblicato} == {b.id for b in carica_catalogo()}


def test_il_sito_non_ruba_le_rotte_al_server(tmp_path, monkeypatch):
    monkeypatch.setenv("BANDI_SITO_DIR", str(tmp_path))
    monkeypatch.setenv("BANDI_RATE_LIMIT", "0")
    from bandi_mcp.http_app import crea_app

    with TestClient(crea_app()) as client:
        assert client.get("/health").json()["stato"] == "ok"
        assert client.get("/").status_code == 200
        assert client.get("/llms.txt").status_code == 200
        # /mcp resta del server MCP: un GET senza gli header giusti è 406, non 404 dello static
        assert client.get("/mcp").status_code != 404
