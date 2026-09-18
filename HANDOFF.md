# HANDOFF — Bandi MCP

Passaggio di consegne da Claude (chat, 18/09/2026) a Claude Code.
Contesto, decisioni prese, cosa funziona, cosa manca, in che ordine.

## Perché esiste

Tesi di Giorgio (nota Granola del 18/09): la prossima interfaccia sono gli agenti, non browser o app.
I prodotti vincenti saranno ricostruiti per agenti, non riadattati con una chat sopra. Primo verticale
scelto: finanza agevolata per PMI del Sud. Motivi: nessun denaro che passa dal prodotto, dominio
strutturabile, utenti (consulenti, commercialisti) che usano già l'AI, distribuzione via clienti ProdG,
coerenza con la missione (portare soldi pubblici alle imprese del Sud).

Il portale è l'interfaccia che perde. Il prodotto è: profilo azienda + server MCP + database normalizzato.
Il fossato è il database.

## Stato al 18/09/2026

Funziona e testato:

- Schema Pydantic v2 (`ProfiloAzienda`, `Bando`, `EsitoAmmissibilita`) con dimensione UE e sezione ATECO calcolate
- Motore deterministico: territorio, dimensione, beneficiario, ATECO ammessi/esclusi, soglie di spesa,
  coerenza categorie, de minimis, requisiti strutturati (automatici/dichiarativi), scadenza rilevante
  oggi, fit 0-100 spiegato, stima lorda, penalità per requisiti bloccanti non verificabili
- 9 tool MCP + 1 resource, verificati con un client `mcp` reale su stdio (tools/list, call_tool,
  errori come `ToolError`, resource read)
- Catalogo: 16 bandi reali con fonti (vedi `data/bandi_sicilia.json`)
- 11 test verdi; demo su tre profili (officina meccanica RG, startup AI CT, hotel ME)

Ranking della demo (sanity check dopo ogni modifica al motore):

- Officina 25.62, 14 ULA, 900k macchinari+digitale → Investimenti Sostenibili 4.0 (96), Nuova Sabatini (84),
  Voucher Cloud (75), ZES (65), Resto al Sud (65, manca `eta_titolare`)
- Startup 62.01, 3 ULA, 2024, innovativa, titolare 29 → Smart&Start (86), Voucher Cloud (85),
  Resto al Sud (80), Sabatini (74), ON (73)
- Hotel 55.10, 22 ULA, 1.8M energia → Conto Termico (89), Green Tour (65, chiude tra 12 gg), Conciliazione (50)

## Decisioni prese (e perché)

| Decisione | Perché |
|---|---|
| Motore senza LLM | Spiegabilità e costo zero per chiamata; l'agente chiamante è già un LLM |
| Profilo tutto opzionale, `campi_mancanti` in output | L'agente deve poter partire da 3 dati e chiedere solo ciò che cambia l'esito |
| Requisiti in due tipi (automatico/dichiarativo) | Metà dei requisiti reali non sono verificabili da dati: vanno esposti, non nascosti |
| Una sola "scadenza rilevante oggi" per bando | Sui bandi cronologici conta la finestra di preparazione, non la chiusura |
| Penalità -25 per requisito bloccante non verificabile | Senza, Resto al Sud saliva a 90 per un'azienda del 2015 solo perché mancava l'età |
| `ToolError` per errori applicativi | In mcp 2.x le eccezioni generiche arrivano all'agente come "Error executing tool" senza dettaglio |
| Campo `calendario` invece di `date` | `date: DateBando` faceva ombra a `datetime.date` e rompeva la generazione dello schema |
| mcp 2.x (`MCPServer`) con fallback 1.x | È quello installato oggi; l'import condizionale evita di pinnare |

## Problemi noti

1. **ZES Unica 2026**: percentuali per regione/dimensione e finestre di comunicazione AdE non verificate
   → `affidabilita_dati: "da_verificare"`, intensità `null`. Da completare da provvedimento AdE.
2. **Brevetti+ 2026**: "in apertura entro settembre", nessuna data pubblicata al 18/09. Ricontrollare.
3. **Investimenti Sostenibili 4.0**: `ateco_ammessi: ["C"]` è un'approssimazione; il decreto 18/03/2026
   ha un elenco di settori manifatturieri ammessi/esclusi da trascrivere.
4. **Conto Termico**: la stima 65% × spesa ignora i massimali per tipologia di intervento → sovrastima.
   Serve una struttura `massimali_per_intervento` o un cap ragionevole.
5. **Resto al Sud 2.0**: manca un requisito sull'impresa nuova/da costituire; oggi un'azienda del 2015
   con titolare 30enne risulterebbe compatibile. Verificare l'avviso e aggiungere il requisito.
6. `dimensione` con soli addetti è ottimista (assume sotto soglia di fatturato): segnalato come avvertenza,
   ma va reso esplicito nello schema.
7. Nessuna regione oltre la Sicilia nel catalogo; `store.py` supporta già più file.
8. Il resource `bandi://catalogo/sicilia` restituisce ~48 KB: valutare paginazione o solo elenco.

## Backlog in ordine di priorità

### P0 — prima di darlo ai tre commercialisti

- [ ] **Chiudere i problemi noti 1-5** (dati). Criterio: nessun bando con `da_verificare` tra i primi 5
      per i tre profili demo; test che copra il requisito "impresa nuova" di Resto al Sud.
- [ ] **`.mcp.json` nel repo + istruzioni di 5 righe** per collegarlo a Claude Desktop e Claude Code.
      Criterio: un commercialista non tecnico ci arriva da solo con il README.
- [ ] **Tool `profilo_da_testo(testo)`**: euristiche (regex) che estraggono P.IVA, ATECO, forma giuridica,
      data costituzione, addetti da una visura incollata come testo. Niente LLM: l'agente ha già letto la visura,
      qui serve solo la normalizzazione. Criterio: test con 3 visure sintetiche.
- [ ] **Log anonimo delle chiamate** (tool, timestamp, esito, n. campi mancanti) in un file locale/SQLite.
      Serve per misurare il test a 2 settimane. Criterio: `scripts/report_uso.py` stampa chiamate/giorno per tool.

### P1 — copertura dati

- [ ] Bandi camerali siciliani (voucher digitalizzazione CCIAA Sud Est, Palermo-Enna, Messina)
- [ ] PR FESR Sicilia 2021-2027 (avvisi Dipartimento Attività Produttive: Digit Imprese, ecc.)
- [ ] GAL siciliani con sportelli aperti
- [ ] Un secondo file `data/bandi_nazionali.json` separando nazionali da regionali
- [ ] Script `scripts/verifica_fonti.py`: apre ogni URL di `fonti`, segnala 404 e schede con
      `ultimo_controllo` > 30 giorni

### P2 — prodotto

- [ ] Ingestione semi-automatica: scraper dei portali → normalizzazione con LLM (fuori dal motore, in uno
      script separato) → PR con `affidabilita_dati: "da_verificare"` → revisione umana → merge
- [ ] `--http` dietro autenticazione (token per consulente) per l'uso senza installazione
- [ ] Profili salvati per consulente (N aziende) + `scadenze_prossime` schedulato la mattina
- [ ] Pubblicazione nelle directory connettori (Claude, ChatGPT apps)

## Non fare

- UI, landing page, dashboard: il prodotto è il server + il dato
- LLM dentro `matcher.py` o nei tool
- Rinominare tool/campi di output senza aggiornare README e test

## Primo prompt suggerito per Claude Code

> Leggi CLAUDE.md e HANDOFF.md. Esegui `python -m pytest -q` e `python scripts/demo.py` per confermare
> lo stato. Poi prendi il P0 "problemi noti 1-5": per ognuno cerca la fonte ufficiale, aggiorna la scheda
> in `data/bandi_sicilia.json` (fonte + `ultimo_controllo` + `affidabilita_dati`), aggiungi un test se
> cambia il comportamento del motore, e rilancia demo e test. Aggiorna la sezione "Stato" di HANDOFF.md
> alla fine. Un commit per problema.
