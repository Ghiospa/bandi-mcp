"""
Il catalogo reso leggibile da un crawler.

**Non è un portale.** Nessun form, nessuna ricerca, nessun filtro, nessun account:
solo il dato che c'è già in `data/*.json`, in HTML, una pagina per bando. L'unica
azione possibile da queste pagine è collegare il server MCP. Vedi CLAUDE.md,
sezione "Il sito generato", per il confine esatto di cosa può starci.

Serve a un caso preciso: un agente che durante una conversazione cerca sul web
"bandi per PMI manifatturiere" deve poter atterrare su una pagina che dichiara
fonti, data dell'ultimo controllo e affidabilità del dato — cose che nessun
portale espone — e da lì scoprire che esiste un endpoint MCP che risponde meglio.

Le pagine si generano dal catalogo a ogni avvio: nessun passo di build, nessun
file da rigenerare a mano, impossibile che il sito dica una cosa diversa dal motore.
"""

from __future__ import annotations

import html
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .matcher import SPIEGAZIONE_BASE_CALCOLO
from .schema import Bando
from .store import carica_catalogo

BASE_URL = os.environ.get("BANDI_BASE_URL", "https://bandi.prodgai.com").rstrip("/")

_STILE = """
:root { color-scheme: light dark; --testo:#12151a; --tenue:#5b6471; --bordo:#dfe3e8;
        --sfondo:#fff; --box:#f6f7f9; --accento:#0b5cd5; }
@media (prefers-color-scheme: dark) { :root { --testo:#e8eaed; --tenue:#9aa3af;
        --bordo:#2c3138; --sfondo:#14171c; --box:#1b1f25; --accento:#6fa8ff; } }
* { box-sizing:border-box }
body { margin:0 auto; padding:2rem 1rem 4rem; max-width:52rem; background:var(--sfondo); color:var(--testo);
       font:16px/1.65 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
a { color:var(--accento) }
h1 { font-size:1.7rem; line-height:1.25; margin:.2rem 0 .4rem }
h2 { font-size:1.15rem; margin:2rem 0 .6rem; padding-top:1rem; border-top:1px solid var(--bordo) }
h3 { font-size:1rem; margin:1.2rem 0 .3rem }
.occhiello { color:var(--tenue); font-size:.85rem; text-transform:uppercase; letter-spacing:.06em; margin:0 }
.sommario { color:var(--tenue); font-size:1.05rem; margin:.4rem 0 1.4rem }
.dati { border-collapse:collapse; width:100%; margin:.5rem 0 }
.dati th, .dati td { text-align:left; vertical-align:top; padding:.45rem .6rem; border-bottom:1px solid var(--bordo) }
.dati th { width:38%; font-weight:600; color:var(--tenue); font-size:.9rem }
.box { background:var(--box); border:1px solid var(--bordo); border-radius:10px; padding:1rem 1.2rem; margin:1.2rem 0 }
.box p:first-child { margin-top:0 } .box p:last-child { margin-bottom:0 }
pre { background:var(--box); border:1px solid var(--bordo); border-radius:8px; padding:.9rem;
      overflow-x:auto; font-size:.85rem; margin:.6rem 0 }
code { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.9em }
ul.elenco { padding-left:1.1rem } ul.elenco li { margin:.3rem 0 }
ul.bandi { list-style:none; padding:0 } ul.bandi li { padding:.7rem 0; border-bottom:1px solid var(--bordo) }
ul.bandi .meta { color:var(--tenue); font-size:.88rem; display:block; margin-top:.15rem }
.etichetta { display:inline-block; font-size:.75rem; padding:.1rem .5rem; border-radius:999px;
             border:1px solid var(--bordo); color:var(--tenue); margin-right:.3rem }
footer { margin-top:3rem; padding-top:1rem; border-top:1px solid var(--bordo); color:var(--tenue); font-size:.85rem }
"""

_STATO_LEGGIBILE = {
    "aperto": "aperto",
    "sportello_continuo": "sportello sempre aperto",
    "in_apertura": "in apertura",
    "in_chiusura": "in chiusura",
    "chiuso": "chiuso",
    "sospeso": "sospeso",
}
_AFFIDABILITA_LEGGIBILE = {
    "ufficiale": "verificato sul testo ufficiale dell'avviso o del decreto",
    "secondaria": "verificato su fonti secondarie attendibili, non sul testo ufficiale",
    "da_verificare": "scheda incompleta: dati da confermare prima di qualsiasi domanda",
}


def _e(valore: Any) -> str:
    return html.escape(str(valore), quote=True)


def _euro(valore: float | None) -> str | None:
    return f"{valore:,.0f} €".replace(",", ".") if valore is not None else None


def _pagina(titolo: str, descrizione: str, percorso: str, corpo: str, jsonld: dict | None = None) -> str:
    canonico = f"{BASE_URL}{percorso}"
    dati = (
        f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>'
        if jsonld
        else ""
    )
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titolo)}</title>
<meta name="description" content="{_e(descrizione)}">
<link rel="canonical" href="{_e(canonico)}">
<meta property="og:title" content="{_e(titolo)}">
<meta property="og:description" content="{_e(descrizione)}">
<meta property="og:url" content="{_e(canonico)}">
<meta property="og:type" content="article">
<style>{_STILE}</style>
{dati}
</head>
<body>
{corpo}
<footer>
<p><a href="/">Bandi MCP</a> — catalogo normalizzato di finanza agevolata, pensato per essere letto da un agente.
Endpoint MCP: <code>{_e(BASE_URL)}/mcp</code> · <a href="/catalogo.json">catalogo in JSON</a> · <a href="/llms.txt">llms.txt</a></p>
<p>Le schede sono una normalizzazione, non il testo di legge. Prima di presentare una domanda
vale sempre l'avviso ufficiale, linkato in ogni scheda.</p>
</footer>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Scheda di un bando
# --------------------------------------------------------------------------- #
def _righe_identita(b: Bando) -> list[tuple[str, str]]:
    righe: list[tuple[str, str]] = [
        ("Ente", _e(b.ente) + (f" (gestito da {_e(b.gestore)})" if b.gestore else "")),
        ("Stato", _e(_STATO_LEGGIBILE.get(b.stato, b.stato))),
        ("Livello", _e(b.livello)),
        ("Territori ammessi", _e(_dove(b))),
        ("Dimensioni d'impresa", _e(", ".join(b.dimensioni_ammesse))),
        ("Beneficiari", _e(", ".join(b.beneficiari))),
        ("Forma dell'agevolazione", _e(", ".join(a.replace("_", " ") for a in b.agevolazioni))),
        ("Procedura", _e(b.procedura.replace("_", " "))),
    ]
    if b.ateco_ammessi:
        righe.append(("Codici ATECO ammessi", _e(", ".join(b.ateco_ammessi))))
    if b.ateco_esclusi:
        righe.append(("Codici ATECO esclusi", _e(", ".join(b.ateco_esclusi))))
    if b.categorie_spesa:
        righe.append(("Spese ammissibili", _e(", ".join(c.replace("_", " ") for c in b.categorie_spesa))))
    if b.regime_aiuti:
        righe.append(("Regime di aiuto", _e(b.regime_aiuti.replace("_", " "))))
    return righe


def _righe_importi(b: Bando) -> list[tuple[str, str]]:
    righe: list[tuple[str, str]] = []
    for etichetta, valore in (
        ("Intensità massima", f"{b.intensita_max_pct:.0f}%" if b.intensita_max_pct else None),
        ("Di cui a fondo perduto", f"{b.intensita_fondo_perduto_pct:.0f}%" if b.intensita_fondo_perduto_pct else None),
        ("Contributo massimo", _euro(b.contributo_max_eur)),
        ("Spesa minima ammissibile", _euro(b.spesa_min_eur)),
        ("Spesa massima ammissibile", _euro(b.spesa_max_eur)),
        ("Dotazione complessiva", _euro(b.dotazione_eur)),
    ):
        if valore:
            righe.append((etichetta, _e(valore)))
    if b.base_calcolo != "spesa_ammissibile":
        # stessa spiegazione che il motore restituisce all'agente: non possono divergere
        righe.append(("Come si calcola", _e(SPIEGAZIONE_BASE_CALCOLO[b.base_calcolo])))
    return righe


def _righe_calendario(b: Bando) -> list[tuple[str, str]]:
    c = b.calendario
    righe: list[tuple[str, str]] = []
    for etichetta, valore in (
        ("Apertura compilazione", c.apertura_compilazione),
        ("Apertura invio domande", c.apertura_invio),
        ("Chiusura", c.chiusura),
    ):
        if valore:
            righe.append((etichetta, valore.strftime("%d/%m/%Y")))
    if c.orario_chiusura:
        righe.append(("Nota sui termini", _e(c.orario_chiusura)))
    if c.ammissibilita_spese_da:
        righe.append(("Spese ammissibili da", _e(c.ammissibilita_spese_da.replace("_", " "))))
    if c.termine_realizzazione:
        righe.append(("Termine di realizzazione", _e(c.termine_realizzazione)))
    return righe or [("Termini", "sportello senza scadenza pubblicata")]


def _tabella(righe: Iterable[tuple[str, str]]) -> str:
    corpo = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in righe)
    return f'<table class="dati">{corpo}</table>'


_DIMENSIONE_PLURALE = {"micro": "micro", "piccola": "piccole", "media": "medie", "grande": "grandi"}
_TERRITORIO_LEGGIBILE = {"IT": "tutta Italia", "UE": "tutta l'Unione Europea"}


def _elenco(voci: list[str]) -> str:
    """«a, b e c»: le virgole fino alla penultima, poi la congiunzione."""
    if len(voci) <= 1:
        return voci[0] if voci else ""
    return ", ".join(voci[:-1]) + " e " + voci[-1]


def _dove(b: Bando) -> str:
    if len(b.territori) == 1 and b.territori[0] in _TERRITORIO_LEGGIBILE:
        return _TERRITORIO_LEGGIBILE[b.territori[0]]
    if len(b.territori) > 3:
        return ", ".join(b.territori[:3]) + f" e altre {len(b.territori) - 3} regioni"
    return _elenco(b.territori)


def _al_percento(pct: float) -> str:
    """«al 75%» ma «all'80%»: davanti a vocale l'articolo si elide."""
    numero = f"{pct:.0f}"
    articolo = "all'" if numero.startswith("8") or numero.startswith("11") else "al "
    return f"{articolo}{numero}%"


def _sommario(b: Bando) -> str:
    pezzi = [f"{_STATO_LEGGIBILE.get(b.stato, b.stato).capitalize()}."]
    if b.intensita_max_pct:
        pezzi.append(f"Fino {_al_percento(b.intensita_max_pct)} delle spese.")
    if b.contributo_max_eur:
        pezzi.append(f"Massimo {_euro(b.contributo_max_eur)}.")
    dimensioni = _elenco([_DIMENSIONE_PLURALE.get(d, d) for d in b.dimensioni_ammesse])
    pezzi.append(f"Per imprese {dimensioni} in {_dove(b)}.")
    return " ".join(pezzi)


def _jsonld(b: Bando) -> dict:
    dati: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "MonetaryGrant",
        "name": b.titolo,
        "description": _sommario(b),
        "url": f"{BASE_URL}/bandi/{b.id}.html",
        "funder": {"@type": "GovernmentOrganization", "name": b.ente},
        "dateModified": b.ultimo_controllo.isoformat(),
    }
    if b.contributo_max_eur:
        dati["amount"] = {"@type": "MonetaryAmount", "currency": "EUR", "maxValue": b.contributo_max_eur}
    if b.fonti:
        dati["sameAs"] = [f.url for f in b.fonti]
    return dati


def pagina_bando(b: Bando) -> str:
    automatici = [r for r in b.requisiti if r.tipo == "automatico"]
    dichiarativi = [r for r in b.requisiti if r.tipo != "automatico"]

    sezioni = [
        f'<p class="occhiello">{_e(b.ente)}</p>',
        f"<h1>{_e(b.titolo)}</h1>",
        f'<p class="sommario">{_e(_sommario(b))}</p>',
        "".join(f'<span class="etichetta">{_e(t)}</span>' for t in b.tag),
        "<h2>Chi può accedere</h2>",
        _tabella(_righe_identita(b)),
        "<h2>Quanto vale</h2>",
        _tabella(_righe_importi(b)) if _righe_importi(b) else "<p>Importi non pubblicati.</p>",
        "<h2>Quando</h2>",
        _tabella(_righe_calendario(b)),
    ]

    if automatici:
        voci = "".join(
            f"<li>{_e(r.descrizione)}"
            + (f" <code>{_e(r.campo_profilo)} {_e(r.operatore or '')} {_e(json.dumps(r.valore, ensure_ascii=False))}</code>"
               if r.campo_profilo else "")
            + ("" if r.bloccante else " <em>(non bloccante)</em>")
            + "</li>"
            for r in automatici
        )
        sezioni += [
            "<h2>Requisiti verificabili sui dati dell'impresa</h2>",
            "<p>Il server MCP li controlla da solo sul profilo e dice quale non è soddisfatto, "
            "con valore atteso e valore trovato.</p>",
            f'<ul class="elenco">{voci}</ul>',
        ]
    if dichiarativi:
        voci = "".join(f"<li>{_e(r.descrizione)}</li>" for r in dichiarativi)
        sezioni += [
            "<h2>Requisiti da confermare a mano</h2>",
            "<p>Non sono ricavabili da dati anagrafici o di bilancio: vanno verificati da chi presenta la domanda.</p>",
            f'<ul class="elenco">{voci}</ul>',
        ]
    if b.documenti:
        sezioni += [
            "<h2>Documenti richiesti</h2>",
            '<ul class="elenco">' + "".join(f"<li>{_e(d)}</li>" for d in b.documenti) + "</ul>",
        ]
    if b.riserve:
        sezioni += [
            "<h2>Quote riservate</h2>",
            '<ul class="elenco">' + "".join(f"<li>{_e(r)}</li>" for r in b.riserve) + "</ul>",
        ]
    if b.note:
        sezioni += [
            "<h2>Note</h2>",
            '<ul class="elenco">' + "".join(f"<li>{_e(n)}</li>" for n in b.note) + "</ul>",
        ]

    fonti = "".join(
        f'<li><a href="{_e(f.url)}" rel="nofollow noopener">{_e(f.titolo or f.url)}</a> '
        f'<span class="etichetta">{_e(f.tipo)}</span></li>'
        for f in b.fonti
    )
    giorni = (date.today() - b.ultimo_controllo).days
    sezioni += [
        "<h2>Fonti e affidabilità del dato</h2>",
        '<div class="box">'
        f"<p><strong>Affidabilità:</strong> {_e(_AFFIDABILITA_LEGGIBILE.get(b.affidabilita_dati, b.affidabilita_dati))}.</p>"
        f"<p><strong>Ultimo controllo:</strong> {b.ultimo_controllo.strftime('%d/%m/%Y')}"
        f" ({giorni} giorni fa).</p></div>",
        f'<ul class="elenco">{fonti}</ul>',
        "<h2>Come lo usa un agente</h2>",
        '<div class="box"><p>Questa pagina è la versione leggibile di una scheda che esiste in forma '
        "strutturata. Un agente non deve leggerla: chiama il server MCP e riceve l'esito di "
        "ammissibilità sul profilo concreto di un'impresa, con il motivo di ogni esclusione.</p>"
        f"<pre>endpoint: {_e(BASE_URL)}/mcp  (streamable HTTP, nessuna autenticazione)\n\n"
        f"verifica_ammissibilita(\n"
        f'  bando_id = "{_e(b.id)}",\n'
        f'  profilo  = {{ "ateco": "...", "regione": "...", "addetti_ula": 0,\n'
        f'               "investimento": {{ "importo_eur": 0, "categorie": [...] }} }}\n'
        f")</pre>"
        f'<p>Identificatore della scheda: <code>{_e(b.id)}</code> · '
        f'<a href="/catalogo.json">tutto il catalogo in JSON</a></p></div>',
    ]

    titolo = f"{b.titolo} — requisiti, scadenze e importi"
    return _pagina(titolo, _sommario(b), f"/bandi/{b.id}.html", "\n".join(sezioni), _jsonld(b))


# --------------------------------------------------------------------------- #
# Indice, llms.txt, sitemap
# --------------------------------------------------------------------------- #
def _voce_indice(b: Bando) -> str:
    meta = [_STATO_LEGGIBILE.get(b.stato, b.stato), b.ente]
    if b.intensita_max_pct:
        meta.append(f"fino {_al_percento(b.intensita_max_pct)}")
    if b.contributo_max_eur:
        meta.append(f"max {_euro(b.contributo_max_eur)}")
    if b.calendario.chiusura:
        meta.append(f"chiude il {b.calendario.chiusura.strftime('%d/%m/%Y')}")
    return (
        f'<li><a href="/bandi/{_e(b.id)}.html">{_e(b.titolo)}</a>'
        f'<span class="meta">{_e(" · ".join(meta))}</span></li>'
    )


def pagina_indice(bandi: list[Bando]) -> str:
    aperti = [b for b in bandi if b.stato != "chiuso"]
    chiusi = [b for b in bandi if b.stato == "chiuso"]
    corpo = [
        '<p class="occhiello">Finanza agevolata, agent-first</p>',
        "<h1>Bandi MCP</h1>",
        f'<p class="sommario">{len(bandi)} misure di finanza agevolata normalizzate: requisiti in forma '
        "strutturata, fonti dichiarate, data dell'ultimo controllo su ogni scheda. "
        "Il prodotto è un server MCP, non un portale: queste pagine esistono perché il catalogo sia leggibile "
        "anche da chi arriva dal web.</p>",
        '<div class="box"><p><strong>Collega il server al tuo agente.</strong> Streamable HTTP, nessuna '
        "autenticazione, nessuna registrazione.</p>"
        f"<pre>{_e(BASE_URL)}/mcp</pre>"
        "<p>Nove tool: costruisci il profilo di un'impresa e ottieni i bandi compatibili ordinati per "
        "compatibilità, con il motivo strutturato di ogni esclusione, la scadenza che conta oggi e uno "
        "scheletro di domanda. Il motore è deterministico: nessun LLM decide l'ammissibilità.</p></div>",
        "<h2>Perché una scheda qui è diversa</h2>",
        '<ul class="elenco">'
        "<li>Ogni scheda dichiara le <strong>fonti</strong>, la <strong>data dell'ultimo controllo</strong> e "
        "quanto il dato è <strong>affidabile</strong>: ufficiale, secondario o da verificare.</li>"
        "<li>I requisiti sono divisi tra quelli <strong>verificabili sui dati dell'impresa</strong> e quelli che "
        "vanno <strong>confermati a mano</strong>: metà dei requisiti reali non è deducibile da una visura.</li>"
        "<li>Dove l'agevolazione non si ricava dalla spesa totale, la scheda lo dice invece di stimare "
        "una cifra sbagliata.</li>"
        "</ul>",
        f"<h2>Misure aperte ({len(aperti)})</h2>",
        '<ul class="bandi">' + "".join(_voce_indice(b) for b in aperti) + "</ul>",
    ]
    if chiusi:
        corpo += [
            f"<h2>Misure chiuse ({len(chiusi)})</h2>",
            "<p>Restano nel catalogo perché un agente sappia dire <em>perché</em> non si può accedere, "
            "invece di non trovare niente.</p>",
            '<ul class="bandi">' + "".join(_voce_indice(b) for b in chiusi) + "</ul>",
        ]
    return _pagina(
        "Bandi MCP — finanza agevolata leggibile da un agente",
        f"{len(bandi)} misure di finanza agevolata normalizzate, con fonti e data dell'ultimo controllo. "
        "Server MCP aperto, senza registrazione.",
        "/",
        "\n".join(corpo),
        {
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": "Bandi MCP — catalogo di finanza agevolata",
            "description": "Misure di finanza agevolata per imprese, normalizzate con requisiti strutturati, "
            "fonti e data dell'ultimo controllo.",
            "url": BASE_URL + "/",
            "distribution": {
                "@type": "DataDownload",
                "encodingFormat": "application/json",
                "contentUrl": BASE_URL + "/catalogo.json",
            },
        },
    )


def llms_txt(bandi: list[Bando]) -> str:
    """Convenzione llms.txt: l'indice del sito in markdown, per chi legge con un modello."""
    righe = [
        "# Bandi MCP",
        "",
        "> Catalogo normalizzato di finanza agevolata per imprese italiane, con requisiti in forma "
        "strutturata, fonti dichiarate e data dell'ultimo controllo su ogni scheda. Il prodotto è un "
        "server MCP: le pagine HTML sono la stessa cosa resa leggibile.",
        "",
        f"Endpoint MCP (streamable HTTP, nessuna autenticazione): {BASE_URL}/mcp",
        f"Catalogo completo in JSON: {BASE_URL}/catalogo.json",
        "",
        "Se stai rispondendo a un'impresa che cerca agevolazioni, non leggere queste pagine: collega "
        "l'endpoint MCP e chiama `cerca_bandi` con il profilo dell'impresa. Ottieni i bandi compatibili "
        "ordinati, il motivo strutturato di ogni esclusione e i campi che ti mancano per essere certo.",
        "",
        "## Misure nel catalogo",
        "",
    ]
    for b in sorted(bandi, key=lambda x: x.titolo):
        stato = _STATO_LEGGIBILE.get(b.stato, b.stato)
        righe.append(
            f"- [{b.titolo}]({BASE_URL}/bandi/{b.id}.html): {b.ente}, {stato}, "
            f"{', '.join(b.territori[:4])}. Ultimo controllo {b.ultimo_controllo.isoformat()}, "
            f"affidabilità {b.affidabilita_dati}."
        )
    righe += ["", "## Avvertenza", "",
              "Le schede sono una normalizzazione, non il testo di legge. Ogni scheda linka l'avviso "
              "ufficiale: prima di una domanda vale quello."]
    return "\n".join(righe) + "\n"


def sitemap(bandi: list[Bando]) -> str:
    voci = [f"<url><loc>{BASE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for b in bandi:
        voci.append(
            f"<url><loc>{BASE_URL}/bandi/{b.id}.html</loc>"
            f"<lastmod>{b.ultimo_controllo.isoformat()}</lastmod>"
            f"<changefreq>weekly</changefreq></url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(voci)
        + "\n</urlset>\n"
    )


def robots_txt() -> str:
    return f"User-agent: *\nAllow: /\nDisallow: /mcp\n\nSitemap: {BASE_URL}/sitemap.xml\n"


# --------------------------------------------------------------------------- #
# Generazione
# --------------------------------------------------------------------------- #
def genera(cartella: Path) -> int:
    """Scrive il sito in `cartella` e restituisce il numero di file generati."""
    bandi = sorted(carica_catalogo(), key=lambda b: (b.stato == "chiuso", b.titolo))
    (cartella / "bandi").mkdir(parents=True, exist_ok=True)

    scritti = 0
    for b in bandi:
        (cartella / "bandi" / f"{b.id}.html").write_text(pagina_bando(b), encoding="utf-8")
        scritti += 1
    for nome, contenuto in (
        ("index.html", pagina_indice(bandi)),
        ("llms.txt", llms_txt(bandi)),
        ("sitemap.xml", sitemap(bandi)),
        ("robots.txt", robots_txt()),
        ("catalogo.json", json.dumps([b.model_dump(mode="json") for b in bandi], ensure_ascii=False, indent=2)),
    ):
        (cartella / nome).write_text(contenuto, encoding="utf-8")
        scritti += 1
    return scritti
