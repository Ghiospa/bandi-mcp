"""
Bandi MCP — server agent-first per la finanza agevolata.

Nessuna interfaccia: l'agente dell'utente (Claude, ChatGPT, altro) chiama questi
tool con il profilo dell'azienda e riceve risposte strutturate, con i motivi.

Avvio:  python -m bandi_mcp.server            (stdio, per Claude Desktop / Claude Code)
        python -m bandi_mcp.server --http     (streamable HTTP su :8000, per client remoti)
"""

from __future__ import annotations

import sys
from datetime import date
from typing import Any, Optional

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore
    from mcp.server.fastmcp.exceptions import ToolError  # type: ignore

from . import matcher
from .schema import Bando, EsitoAmmissibilita, ProfiloAzienda
from .store import carica_catalogo, ricarica, trova_bando

ISTRUZIONI = """\
Bandi MCP: finanza agevolata per imprese siciliane, pensata per essere usata da un agente.

Flusso consigliato:
1. schema_profilo() per sapere quali dati servono, poi costruisci il ProfiloAzienda
   dalla conversazione, dalla P.IVA (visura, bilancio) e dal sito dell'azienda. Non chiedere
   all'utente di compilare un form: raccogli i campi che mancano solo se cambiano l'esito.
2. cerca_bandi(profilo) restituisce i bandi compatibili ordinati per fit, con motivi e scadenze.
3. verifica_ammissibilita(bando_id, profilo) per il dettaglio di un singolo bando.
4. requisiti_documentali(bando_id) per la checklist e le date che contano.
5. bozza_domanda(bando_id, profilo, progetto) per uno scheletro di domanda da completare.

Ogni scheda ha fonti e data dell'ultimo controllo: prima di una domanda vera, rimanda sempre al
testo ufficiale dell'avviso. Le stime economiche sono lorde: i contributi a fondo perduto sono tassati.
"""

server = _Server(
    name="bandi-mcp",
    title="Bandi MCP — finanza agevolata agent-first (Sicilia)",
    instructions=ISTRUZIONI,
    version="0.1.0",
)


def _profilo(p: dict[str, Any] | ProfiloAzienda) -> ProfiloAzienda:
    if isinstance(p, ProfiloAzienda):
        return p
    try:
        return ProfiloAzienda.model_validate(p)
    except Exception as exc:  # pydantic.ValidationError
        raise ToolError(f"Profilo non valido: {exc}. Chiama schema_profilo() per lo schema atteso.") from exc


def _bando_or_error(bando_id: str) -> Bando:
    b = trova_bando(bando_id)
    if b is None:
        ids = [x.id for x in carica_catalogo()]
        raise ToolError(f"Bando '{bando_id}' non trovato. ID disponibili: {ids}")
    return b


def _bando_breve(b: Bando) -> dict[str, Any]:
    return {
        "id": b.id,
        "titolo": b.titolo,
        "ente": b.ente,
        "livello": b.livello,
        "stato": b.stato,
        "procedura": b.procedura,
        "agevolazioni": b.agevolazioni,
        "intensita_max_pct": b.intensita_max_pct,
        "contributo_max_eur": b.contributo_max_eur,
        "spesa_min_eur": b.spesa_min_eur,
        "spesa_max_eur": b.spesa_max_eur,
        "categorie_spesa": b.categorie_spesa,
        "tag": b.tag,
    }


# --------------------------------------------------------------------------- #
# Tool
# --------------------------------------------------------------------------- #
@server.tool(
    name="schema_profilo",
    description=(
        "Restituisce lo schema JSON del ProfiloAzienda atteso dagli altri tool, con una guida su come "
        "ricavare ogni campo (visura, bilancio, conversazione). Chiamalo una volta prima di cerca_bandi."
    ),
)
def schema_profilo() -> dict[str, Any]:
    return {
        "json_schema": ProfiloAzienda.model_json_schema(),
        "campi_minimi_per_una_prima_ricerca": ["regione", "ateco", "addetti_ula", "investimento.categorie", "investimento.importo_eur"],
        "campi_che_sbloccano_molti_bandi": [
            "data_costituzione (startup / nuove imprese)",
            "eta_titolare e compagine_giovanile_under36 (Resto al Sud, ON)",
            "startup_innovativa (Smart&Start)",
            "dipendenti_totali (formazione, conciliazione)",
            "de_minimis_ricevuti_36_mesi_eur (tutti i bandi de minimis; si legge sul Registro Nazionale Aiuti)",
            "connettivita_mbps (Voucher Cloud)",
        ],
        "come_ricavarli": {
            "ateco, forma_giuridica, data_costituzione, addetti": "visura camerale",
            "fatturato, totale_bilancio, mol": "ultimo bilancio depositato (per società di capitali)",
            "de_minimis_ricevuti_36_mesi_eur": "RNA - Registro Nazionale Aiuti (rna.gov.it), sezione trasparenza",
            "investimento": "conversazione con l'imprenditore: cosa vuole fare, quanto, quando",
        },
        "esempio": {
            "ragione_sociale": "Officine Meccaniche Iblee srl",
            "ateco": "25.62",
            "forma_giuridica": "srl",
            "regione": "Sicilia",
            "provincia": "RG",
            "addetti_ula": 14,
            "fatturato_ultimo_eur": 2100000,
            "data_costituzione": "2015-03-10",
            "dipendenti_totali": 14,
            "durc_regolare": True,
            "connettivita_mbps": 100,
            "investimento": {"importo_eur": 900000, "categorie": ["macchinari", "digitale"], "descrizione": "Nuova linea CNC con MES"},
        },
    }


@server.tool(
    name="cerca_bandi",
    description=(
        "Cerca i bandi compatibili con un ProfiloAzienda e li ordina per punteggio di fit. Per ogni bando restituisce "
        "esito (ammissibile / ammissibile_con_verifiche / dati_insufficienti), motivi strutturati, campi mancanti, "
        "prossima scadenza con giorni rimanenti e stima lorda dell'agevolazione. "
        "Usa includi_esclusi=true per vedere anche i bandi scartati con il motivo di esclusione."
    ),
)
def cerca_bandi(
    profilo: dict[str, Any],
    includi_esclusi: bool = False,
    limite: int = 10,
    solo_tag: Optional[list[str]] = None,
) -> dict[str, Any]:
    p = _profilo(profilo)
    bandi = carica_catalogo()
    if solo_tag:
        wanted = {t.lower() for t in solo_tag}
        bandi = [b for b in bandi if wanted & {t.lower() for t in b.tag}]
    esiti = matcher.classifica(bandi, p, solo_compatibili=not includi_esclusi)
    compatibili = [e for e in esiti if e.esito != "non_ammissibile"]
    esclusi = [e for e in esiti if e.esito == "non_ammissibile"]

    # campi che, se forniti, cambierebbero l'esito di più bandi
    conteggio: dict[str, int] = {}
    for e in compatibili:
        for c in e.campi_mancanti:
            conteggio[c] = conteggio.get(c, 0) + 1
    da_chiedere = sorted(conteggio.items(), key=lambda kv: -kv[1])[:5]

    return {
        "profilo_riconosciuto": {
            "ragione_sociale": p.ragione_sociale,
            "regione": p.regione,
            "ateco": p.ateco,
            "sezione_ateco": p.sezione_ateco,
            "dimensione": p.dimensione,
            "eta_impresa_mesi": p.eta_impresa_mesi,
            "investimento": p.investimento.model_dump(mode="json"),
        },
        "totale_catalogo": len(carica_catalogo()),
        "compatibili": [e.model_dump(mode="json") for e in compatibili[:limite]],
        "esclusi": [
            {"bando_id": e.bando_id, "titolo": e.titolo, "motivo": e.motivi_esclusione[0].model_dump(mode="json") if e.motivi_esclusione else None}
            for e in esclusi
        ] if includi_esclusi else [],
        "dati_che_migliorerebbero_la_ricerca": [{"campo": c, "bandi_interessati": n} for c, n in da_chiedere],
        "data_valutazione": date.today().isoformat(),
    }


@server.tool(
    name="verifica_ammissibilita",
    description=(
        "Valuta in dettaglio un singolo bando rispetto al ProfiloAzienda: requisiti superati, motivi di esclusione "
        "strutturati (campo, atteso, trovato), avvertenze non bloccanti, verifiche da fare a mano, campi mancanti, "
        "fattori del punteggio e scadenza rilevante."
    ),
)
def verifica_ammissibilita(bando_id: str, profilo: dict[str, Any]) -> dict[str, Any]:
    b = _bando_or_error(bando_id)
    p = _profilo(profilo)
    esito: EsitoAmmissibilita = matcher.valuta(b, p)
    return {
        "esito": esito.model_dump(mode="json"),
        "bando": _bando_breve(b),
        "regime_aiuti": b.regime_aiuti,
        "riserve": b.riserve,
        "note_operative": b.note,
        "fonti": [f.model_dump() for f in b.fonti],
        "ultimo_controllo": b.ultimo_controllo.isoformat(),
        "affidabilita_dati": b.affidabilita_dati,
    }


@server.tool(
    name="dettaglio_bando",
    description="Restituisce la scheda completa normalizzata di un bando (tutti i campi, requisiti strutturati, fonti).",
)
def dettaglio_bando(bando_id: str) -> dict[str, Any]:
    b = _bando_or_error(bando_id)
    d = b.model_dump(mode="json")
    d["scadenza_rilevante_oggi"] = matcher.calcola_scadenza(b).model_dump(mode="json")
    return d


@server.tool(
    name="requisiti_documentali",
    description=(
        "Checklist documentale di un bando e le tre date che contano (compilazione, invio, ammissibilità delle spese), "
        "con le trappole tipiche (DURC 120 giorni, firma digitale, spese anticipate, de minimis)."
    ),
)
def requisiti_documentali(bando_id: str) -> dict[str, Any]:
    b = _bando_or_error(bando_id)
    scad = matcher.calcola_scadenza(b)
    trappole = [
        "Il DURC vale 120 giorni dalla verifica: controllare che sia valido al giorno dell'invio",
        "Firma digitale: verificare la scadenza del certificato prima della finestra",
    ]
    if b.calendario.ammissibilita_spese_da == "presentazione_domanda":
        trappole.append("Ordini firmati, acconti o fatture PRIMA dell'invio rendono quelle spese non ammissibili")
    if b.calendario.ammissibilita_spese_da == "richiesta_preliminare":
        trappole.append("Serve la richiesta preliminare prima di avviare i lavori")
    if b.calendario.ammissibilita_spese_da == "pec_domanda_banca":
        trappole.append("L'investimento va avviato dopo la PEC di domanda alla banca, non dopo la concessione")
    if b.regime_aiuti == "de_minimis":
        trappole.append("Controllare il plafond de minimis residuo (300.000 € su triennio mobile) sul Registro Nazionale Aiuti")
    if b.procedura in ("cronologico", "cronologico_giornaliero"):
        trappole.append("Procedura cronologica: preventivi e allegati vanno chiusi PRIMA dell'apertura, non durante")
    if b.procedura in ("valutativa", "graduatoria"):
        trappole.append("Procedura valutativa: la data di invio non dà punteggio, conta la qualità del progetto e del piano economico")
    if "fondo_perduto" in b.agevolazioni:
        trappole.append("Il contributo a fondo perduto è tassato (IRES/IRAP) salvo esclusione espressa: la copertura reale è inferiore a quella nominale")
    return {
        "bando": _bando_breve(b),
        "documenti": b.documenti,
        "requisiti_dichiarativi_da_confermare": [r.descrizione for r in b.requisiti if r.tipo == "dichiarativo"],
        "date": b.calendario.model_dump(mode="json"),
        "scadenza_rilevante_oggi": scad.model_dump(mode="json"),
        "piattaforma": b.piattaforma,
        "trappole_ricorrenti": trappole,
        "fonti": [f.model_dump() for f in b.fonti],
        "ultimo_controllo": b.ultimo_controllo.isoformat(),
    }


@server.tool(
    name="scadenze_prossime",
    description=(
        "Elenca gli eventi (aperture compilazione, aperture invio, chiusure) dei prossimi N giorni. "
        "Con un profilo, filtra sui bandi compatibili. Senza profilo, tutto il catalogo."
    ),
)
def scadenze_prossime(giorni: int = 60, profilo: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    oggi = date.today()
    bandi = carica_catalogo()
    esiti_per_id: dict[str, EsitoAmmissibilita] = {}
    if profilo:
        p = _profilo(profilo)
        for e in matcher.classifica(bandi, p, solo_compatibili=True):
            esiti_per_id[e.bando_id] = e
        bandi = [b for b in bandi if b.id in esiti_per_id]

    eventi: list[dict[str, Any]] = []
    for b in bandi:
        for evento, d in (
            ("apertura_compilazione", b.calendario.apertura_compilazione),
            ("apertura_invio", b.calendario.apertura_invio),
            ("chiusura", b.calendario.chiusura),
        ):
            if d and 0 <= (d - oggi).days <= giorni:
                eventi.append(
                    {
                        "data": d.isoformat(),
                        "giorni_rimanenti": (d - oggi).days,
                        "evento": evento,
                        "bando_id": b.id,
                        "titolo": b.titolo,
                        "orario": b.calendario.orario_chiusura if evento == "chiusura" else None,
                        "procedura": b.procedura,
                        "fit": esiti_per_id[b.id].punteggio_fit if b.id in esiti_per_id else None,
                    }
                )
    eventi.sort(key=lambda e: e["data"])
    sportelli = [
        {"bando_id": b.id, "titolo": b.titolo, "fit": esiti_per_id[b.id].punteggio_fit if b.id in esiti_per_id else None}
        for b in bandi
        if b.stato == "sportello_continuo"
    ]
    return {"oggi": oggi.isoformat(), "orizzonte_giorni": giorni, "eventi": eventi, "sportelli_sempre_aperti": sportelli}


@server.tool(
    name="bozza_domanda",
    description=(
        "Genera lo scheletro strutturato di una domanda per un bando: sezioni, dati già disponibili dal profilo, "
        "dati mancanti da raccogliere, istruzioni per ogni sezione e avvertenze. L'agente lo completa in linguaggio "
        "naturale; questo tool non scrive prosa, prepara la struttura e i controlli."
    ),
)
def bozza_domanda(bando_id: str, profilo: dict[str, Any], progetto: Optional[str] = None) -> dict[str, Any]:
    b = _bando_or_error(bando_id)
    p = _profilo(profilo)
    esito = matcher.valuta(b, p)
    if esito.esito == "non_ammissibile":
        return {
            "bloccato": True,
            "motivo": esito.motivi_esclusione[0].model_dump(mode="json") if esito.motivi_esclusione else "non ammissibile",
            "suggerimento": "Non ha senso preparare la domanda: proponi al cliente i bandi compatibili di cerca_bandi.",
        }

    imp = p.investimento.importo_eur
    piano_spese = {
        "categorie_ammissibili": b.categorie_spesa,
        "categorie_previste_dal_cliente": p.investimento.categorie,
        "fuori_perimetro": sorted(set(p.investimento.categorie) - set(b.categorie_spesa)),
        "importo_totale_eur": imp,
        "vincoli": {"spesa_min_eur": b.spesa_min_eur, "spesa_max_eur": b.spesa_max_eur, "contributo_max_eur": b.contributo_max_eur},
        "istruzioni": "Una riga per voce di spesa: descrizione, fornitore, importo, categoria ammissibile, preventivo allegato. Almeno tre preventivi confrontabili per le voci rilevanti dove richiesto.",
    }

    sezioni = [
        {
            "sezione": "1. Anagrafica e requisiti soggettivi",
            "dati_disponibili": {
                "ragione_sociale": p.ragione_sociale, "partita_iva": p.partita_iva, "forma_giuridica": p.forma_giuridica,
                "ateco": p.ateco, "sede": f"{p.comune or ''} ({p.provincia or ''}) {p.regione or ''}".strip(),
                "dimensione": p.dimensione, "addetti_ula": p.addetti_ula, "data_costituzione": p.data_costituzione,
            },
            "dati_mancanti": esito.campi_mancanti,
            "istruzioni": "Compilare dalla visura. La dimensione d'impresa segue la Racc. 2003/361 (addetti + fatturato o bilancio).",
        },
        {
            "sezione": "2. Descrizione del progetto",
            "dati_disponibili": {"descrizione_cliente": progetto or p.investimento.descrizione},
            "dati_mancanti": [] if (progetto or p.investimento.descrizione) else ["descrizione del progetto"],
            "istruzioni": (
                "Problema che l'investimento risolve, soluzione, risultati attesi misurabili. Usare il lessico del bando: "
                + ", ".join(b.tag)
                + ". Collegare esplicitamente ogni voce di spesa a un obiettivo della misura."
            ),
        },
        {
            "sezione": "3. Coerenza con gli obiettivi della misura",
            "dati_disponibili": {"riserve_e_premialita": b.riserve, "requisiti_dichiarativi": [r.descrizione for r in b.requisiti if r.tipo == "dichiarativo"]},
            "dati_mancanti": [],
            "istruzioni": "Dimostrare, con evidenze, ogni requisito dichiarativo. Se l'azienda rientra in una riserva, dirlo nella prima frase.",
        },
        {"sezione": "4. Piano delle spese", "dati_disponibili": piano_spese, "dati_mancanti": [] if imp else ["investimento.importo_eur"], "istruzioni": piano_spese["istruzioni"]},
        {
            "sezione": "5. Cronoprogramma",
            "dati_disponibili": {"avvio_previsto": p.investimento.avvio_previsto, "date_bando": b.calendario.model_dump(mode="json"), "termine_realizzazione": b.calendario.termine_realizzazione},
            "dati_mancanti": [] if p.investimento.avvio_previsto else ["investimento.avvio_previsto"],
            "istruzioni": "Nessuna spesa prima della data di ammissibilità. Fasi con milestone verificabili e coerenti con il termine di realizzazione.",
        },
        {
            "sezione": "6. Sostenibilità economico-finanziaria",
            "dati_disponibili": {
                "fatturato_ultimo_eur": p.fatturato_ultimo_eur, "fatturato_medio_2_esercizi_eur": p.fatturato_medio_2_esercizi_eur,
                "mol_ultimi_2_esercizi_eur": p.mol_ultimi_2_esercizi_eur, "stima_agevolazione_lorda_eur": esito.stima_agevolazione_eur,
                "quota_a_carico_eur": (imp - esito.stima_agevolazione_eur) if (imp and esito.stima_agevolazione_eur) else None,
            },
            "dati_mancanti": [c for c in ("fatturato_ultimo_eur", "mol_ultimi_2_esercizi_eur") if getattr(p, c) is None],
            "istruzioni": "Fonti e impieghi: come si copre la quota non agevolata. Nel piano di cassa considerare che il contributo è tassato e arriva dopo la rendicontazione.",
        },
        {
            "sezione": "7. Allegati",
            "dati_disponibili": {"documenti_richiesti": b.documenti},
            "dati_mancanti": [],
            "istruzioni": "Un PDF per documento, firmato digitalmente dove previsto. Verificare la leggibilità su un secondo dispositivo prima dell'invio.",
        },
    ]

    avvertenze = [a.descrizione for a in esito.avvertenze] + esito.verifiche_manuali
    if b.procedura in ("cronologico", "cronologico_giornaliero") and esito.prossima_scadenza.evento == "apertura_invio":
        avvertenze.append(
            f"Procedura cronologica: la finestra utile sono i {esito.prossima_scadenza.giorni_rimanenti} giorni PRIMA del {esito.prossima_scadenza.data:%d/%m/%Y}. Arrivare all'invio con la pratica già validata."
        )

    return {
        "bando": _bando_breve(b),
        "esito_ammissibilita": esito.esito,
        "punteggio_fit": esito.punteggio_fit,
        "scadenza_rilevante": esito.prossima_scadenza.model_dump(mode="json"),
        "sezioni": sezioni,
        "avvertenze": avvertenze,
        "prossimo_passo": (
            "Raccogliere i dati mancanti e i preventivi, poi far leggere il testo ufficiale dell'avviso al consulente: "
            + ", ".join(f.url for f in b.fonti if f.tipo == "ufficiale")
        ),
    }


@server.tool(
    name="elenco_bandi",
    description="Elenco sintetico di tutto il catalogo (id, titolo, stato, agevolazioni, tag). Utile per orientarsi o per scegliere solo_tag in cerca_bandi.",
)
def elenco_bandi(stato: Optional[str] = None) -> dict[str, Any]:
    bandi = carica_catalogo()
    if stato:
        bandi = [b for b in bandi if b.stato == stato]
    return {
        "totale": len(bandi),
        "bandi": [{**_bando_breve(b), "scadenza_rilevante_oggi": matcher.calcola_scadenza(b).model_dump(mode="json")} for b in bandi],
        "tag_disponibili": sorted({t for b in carica_catalogo() for t in b.tag}),
    }


@server.tool(name="ricarica_catalogo", description="Ricarica i file JSON del catalogo da disco (dopo un aggiornamento dati). Restituisce il numero di bandi.")
def ricarica_catalogo() -> dict[str, int]:
    return {"bandi_caricati": ricarica()}


# --------------------------------------------------------------------------- #
# Resource: il catalogo grezzo, per chi vuole leggerlo tutto
# --------------------------------------------------------------------------- #
@server.resource("bandi://catalogo/sicilia", description="Catalogo completo dei bandi normalizzati (JSON)")
def risorsa_catalogo() -> str:
    import json

    return json.dumps([b.model_dump(mode="json") for b in carica_catalogo()], ensure_ascii=False, indent=2)


def main() -> None:
    if "--http" in sys.argv:
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
