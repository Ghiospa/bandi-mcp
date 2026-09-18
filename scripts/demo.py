"""
Demo senza MCP: chiama i tool come funzioni Python su tre profili tipo.
Uso:  python scripts/demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bandi_mcp import server  # noqa: E402

PROFILI = {
    "officina_meccanica_ragusa": {
        "ragione_sociale": "Officine Meccaniche Iblee srl",
        "ateco": "25.62",
        "forma_giuridica": "srl",
        "regione": "Sicilia",
        "provincia": "RG",
        "addetti_ula": 14,
        "fatturato_ultimo_eur": 2_100_000,
        "data_costituzione": "2015-03-10",
        "dipendenti_totali": 14,
        "durc_regolare": True,
        "connettivita_mbps": 100,
        "investimento": {
            "importo_eur": 900_000,
            "categorie": ["macchinari", "digitale"],
            "descrizione": "Nuova linea CNC con MES e manutenzione predittiva",
            "avvio_previsto": "2026-11-15",
        },
    },
    "startup_ai_catania": {
        "ragione_sociale": "Agenti Iblei srl",
        "ateco": "62.01",
        "forma_giuridica": "srl",
        "regione": "Sicilia",
        "provincia": "CT",
        "addetti_ula": 3,
        "fatturato_ultimo_eur": 120_000,
        "data_costituzione": "2024-06-01",
        "startup_innovativa": True,
        "compagine_giovanile_under36": True,
        "eta_titolare": 29,
        "dipendenti_totali": 2,
        "durc_regolare": True,
        "connettivita_mbps": 200,
        "de_minimis_ricevuti_36_mesi_eur": 0,
        "investimento": {
            "importo_eur": 180_000,
            "categorie": ["digitale", "assunzioni", "cloud_cyber"],
            "descrizione": "Sviluppo piattaforma agenti AI per PMI, 2 assunzioni",
        },
    },
    "hotel_taormina": {
        "ragione_sociale": "Hotel Belvedere Etna sas",
        "ateco": "55.10",
        "forma_giuridica": "sas",
        "regione": "Sicilia",
        "provincia": "ME",
        "addetti_ula": 22,
        "fatturato_ultimo_eur": 3_400_000,
        "data_costituzione": "2008-01-15",
        "dipendenti_totali": 22,
        "durc_regolare": True,
        "investimento": {
            "importo_eur": 1_800_000,
            "categorie": ["riqualificazione_turistica", "efficienza_energetica", "rinnovabili"],
            "descrizione": "Riqualificazione energetica con fotovoltaico e pompe di calore",
        },
    },
}


def stampa(titolo: str, obj) -> None:
    print("\n" + "=" * 88)
    print(titolo)
    print("=" * 88)
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    print(f"Catalogo: {server.elenco_bandi()['totale']} bandi")

    for nome, profilo in PROFILI.items():
        ris = server.cerca_bandi(profilo, includi_esclusi=True, limite=5)
        print("\n" + "#" * 88)
        print(f"# {nome}  ->  dimensione={ris['profilo_riconosciuto']['dimensione']}  sezione ATECO={ris['profilo_riconosciuto']['sezione_ateco']}")
        print("#" * 88)
        for e in ris["compatibili"]:
            s = e["prossima_scadenza"]
            print(f"  [{e['punteggio_fit']:>3}] {e['esito']:<26} {e['titolo']}")
            print(f"        {e['sintesi']}")
            if e["campi_mancanti"]:
                print(f"        mancano: {', '.join(e['campi_mancanti'])}")
        print("  -- esclusi:")
        for x in ris["esclusi"]:
            m = x["motivo"] or {}
            print(f"        {x['titolo']}: {m.get('descrizione')} (atteso {m.get('atteso')}, trovato {m.get('trovato')})")
        if ris["dati_che_migliorerebbero_la_ricerca"]:
            print(f"  -- da chiedere: {ris['dati_che_migliorerebbero_la_ricerca']}")

    stampa("verifica_ammissibilita: officina -> Investimenti Sostenibili 4.0",
           server.verifica_ammissibilita("mimit-investimenti-sostenibili-40-2026", PROFILI["officina_meccanica_ragusa"])["esito"])

    stampa("requisiti_documentali: Voucher Cloud",
           server.requisiti_documentali("mimit-voucher-cloud-cybersecurity-2026"))

    stampa("scadenze_prossime (60 gg) per la startup",
           server.scadenze_prossime(60, PROFILI["startup_ai_catania"]))

    bozza = server.bozza_domanda("mimit-investimenti-sostenibili-40-2026", PROFILI["officina_meccanica_ragusa"])
    stampa("bozza_domanda: sezioni e avvertenze (officina)",
           {"sezioni": [s["sezione"] for s in bozza["sezioni"]], "avvertenze": bozza["avvertenze"], "prossimo_passo": bozza["prossimo_passo"]})
