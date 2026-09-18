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

- Schema Pydantic v2 con dimensione UE, sezione ATECO e impresa nuova/da costituire calcolate
- Motore deterministico: territorio, dimensione, beneficiario, ATECO ammessi/esclusi, soglie di spesa,
  coerenza categorie, de minimis, requisiti strutturati, scadenza rilevante oggi, fit 0-100 spiegato,
  stima lorda solo dove ha senso darla (`base_calcolo`), penalità per requisiti bloccanti non verificabili
- 9 tool MCP + 1 resource, verificati con un client `mcp` reale su stdio e su HTTP
- **Endpoint HTTP pronto per il deploy pubblico**: rate limit per IP, host ammessi, `/health`,
  log anonimo delle chiamate. Dockerfile, railway.json, render.yaml. Vedi `DEPLOY.md`
- **Sito generato dal catalogo**: una pagina per bando, indice, llms.txt, sitemap, catalogo.json.
  Rigenerato a ogni avvio, servito dallo stesso processo
- Catalogo: 26 schede (9 ufficiali, 13 secondarie, 4 da verificare) in due file, nazionali e Sicilia
- 37 test verdi; demo su tre profili; `verifica_fonti.py` conferma 48 fonti su 48 raggiungibili

Ranking della demo (sanity check dopo ogni modifica al motore):

- Officina 25.62, 14 ULA, 900k → Investimenti Sostenibili 4.0 (96), Nuova Sabatini (84),
  Transizione 5.0 (80), Voucher Cloud (75), SIMEST (74)
- Startup 62.01, 3 ULA, 2024 → Smart&Start (86), Voucher Cloud (85), SIMEST (74), Sabatini (74), ON (73)
- Hotel 55.10, 22 ULA, 1.8M energia → Conto Termico (89, senza stima), Transizione 5.0 (80),
  Green Tour (65), Fondo di garanzia (63), Conciliazione (50)

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

Chiusi il 18/09/2026 (un commit per problema, vedi `git log`):

1. ~~ZES Unica 2026~~ → finestra di comunicazione preventiva 31/03-30/05/2026 chiusa (fonte AdE),
   integrativa 03/01-17/01/2027 solo per chi ha già comunicato. Scheda a `stato: "chiuso"`, aliquote
   Sicilia 40/50/60%, soglie 200k-100M. Una riapertura 2027 dipende dalla legge di bilancio.
2. ~~Brevetti+ 2026~~ → decreto direttoriale MIMIT 28/07/2026 (GU 200 del 29/08/2026), 20 M€.
   Gli avvisi attuativi DGIAI non risultano pubblicati: la scheda resta `da_verificare` per scelta,
   non per mancanza di ricerca. **Da ricontrollare: è l'unica scheda ancora da verificare.**
3. ~~Investimenti Sostenibili 4.0~~ → allegato 4 del DM 18/03/2026 trascritto dal decreto: sezione C
   più 17 codici di servizi alle imprese. Esclusioni settoriali in `ateco_esclusi`, esclusioni di
   progetto (allegato 6, tetto del 70% del fatturato, finalità del programma) come dichiarativi.
4. ~~Conto Termico~~ → nuovo campo `base_calcolo: "massimali_specifici"`: il motore non stima più
   il 65% del totale (erano 1,17 M€ sull'hotel) e rimanda alle tabelle €/kW e €/m².
5. ~~Resto al Sud 2.0~~ → requisito `IMPRESA_NUOVA` su un nuovo computed field
   `impresa_nuova_o_da_costituire`, più i dichiarativi su inattività, condizione soggettiva del
   richiedente e sede operativa.

Ancora aperti:

6. `dimensione` con soli addetti è ottimista (assume sotto soglia di fatturato): segnalato come avvertenza,
   ma va reso esplicito nello schema.
7. Nessuna regione oltre la Sicilia nel catalogo; `store.py` supporta già più file.
8. Il resource `bandi://catalogo/sicilia` restituisce ~50 KB: valutare paginazione o solo elenco.
9. `eta_impresa_mesi` e `impresa_nuova_o_da_costituire` usano `date.today()`, non il parametro `oggi`
   di `valuta()`: i test che simulano una data diversa da oggi non li vedono cambiare.
10. Le aliquote ZES per dimensione (40/50/60%) stanno in una nota: il motore usa il massimo (60%) per
    tutti. Se servisse precisione, serve un campo `intensita_per_dimensione`.

## Backlog in ordine di priorità

### P0 — prima di darlo ai tre commercialisti

- [x] **Chiudere i problemi noti 1-5** (dati) — fatto il 18/09/2026. Criterio rispettato: nessun bando
      con `da_verificare` tra i primi 5 per i tre profili demo, e tre test nuovi sul requisito
      "impresa nuova" di Resto al Sud.
- [x] **`.mcp.json` nel repo + istruzioni** — fatto. Il file aveva `"type": "stdio"`, che faceva fallire
      il collegamento in Claude Code, e `python`, che su macOS non esiste. Con l'endpoint pubblico la
      strada per un non tecnico è ancora più corta: un solo URL, niente da installare (vedi `DEPLOY.md`).
- [x] **Log anonimo delle chiamate** — fatto, `bandi_mcp/uso.py` come middleware MCP e
      `scripts/report_uso.py` per leggerlo. Registra tool, esito, durata e due conteggi; niente del
      profilo, con un test che fallisce se qualcuno aggiunge una colonna identificabile.
- [ ] **Tool `profilo_da_testo(testo)`**: euristiche (regex) che estraggono P.IVA, ATECO, forma giuridica,
      data costituzione, addetti da una visura incollata come testo. Niente LLM: l'agente ha già letto la
      visura, qui serve solo la normalizzazione. Criterio: test con 3 visure sintetiche.
- [ ] **Deploy vero su bandi.prodgai.com**: richiede account e DNS, vedi `DEPLOY.md`. Il Dockerfile non è
      mai stato costruito (Docker non disponibile sulla macchina di sviluppo).

### P1 — copertura dati

Il catalogo è il fossato: 26 schede sono un inizio, non un prodotto.

- [x] Un secondo file `data/bandi_nazionali.json` separando nazionali da regionali — fatto, 10 schede
- [x] Script `scripts/verifica_fonti.py`: apre ogni URL di `fonti`, segnala 404 e schede con
      `ultimo_controllo` oltre soglia. Esce con codice 1, da mettere in CI settimanale
- [ ] **Altre misure nazionali già individuate e non ancora inserite**: Fondo impresa femminile,
      Contratto di sviluppo, Economia circolare, Italia Economia Sociale, Voucher 3I, credito d'imposta
      incubatori e acceleratori certificati, FRI-Tur e turismo, ISMEA per l'agricoltura, ICE per l'export,
      Fondo Nuove Competenze, le singole linee SIMEST (oggi c'è una scheda ombrello sola)
- [ ] Bandi camerali siciliani (voucher digitalizzazione CCIAA Sud Est, Palermo-Enna, Messina)
- [ ] PR FESR Sicilia 2021-2027 (avvisi Dipartimento Attività Produttive: Digit Imprese, ecc.)
- [ ] GAL siciliani con sportelli aperti
- [ ] Smaltire le 4 schede `da_verificare`: Brevetti+, Disegni+, Marchi+ (avvisi attuativi attesi
      entro fine settembre 2026) e filiera moda (decreto direttoriale non pubblicato)

### P2 — prodotto e distribuzione

- [x] `--http` per l'uso senza installazione — fatto, ma **aperto senza autenticazione** per scelta:
      ogni attrito taglia l'adozione, e il rate limit per IP basta finché l'istanza è una
- [ ] Pubblicazione nel registry MCP ufficiale (`server.json` è pronto, namespace `com.prodgai/bandi`,
      serve l'autenticazione DNS sul dominio apex) e nelle directory PulseMCP, Glama, Smithery, mcp.so.
      **Da fare per ultimo**: le schede vengono messe in cache e la prima impressione si brucia una volta
- [ ] Google Search Console e Bing Webmaster Tools con la sitemap, più qualche link in entrata reale
- [ ] Ingestione semi-automatica: scraper dei portali → normalizzazione con LLM (fuori dal motore, in uno
      script separato) → PR con `affidabilita_dati: "da_verificare"` → revisione umana → merge
- [ ] Profili salvati per consulente (N aziende) + `scadenze_prossime` schedulato la mattina
- [ ] Rate limit e log condivisi, se un giorno le istanze diventano più di una: oggi sono in memoria

## Non fare

- Una UI applicativa. Il sito generato è il catalogo reso leggibile ai crawler, non un portale:
  niente form, niente ricerca, niente filtri, niente account. Il confine è in `CLAUDE.md`
- LLM dentro `matcher.py` o nei tool
- Rinominare tool/campi di output senza aggiornare README e test

## Primo prompt suggerito per Claude Code

> Leggi CLAUDE.md e HANDOFF.md. Esegui `python -m pytest -q` e `python scripts/demo.py` per confermare
> lo stato. Poi prendi il P0 "problemi noti 1-5": per ognuno cerca la fonte ufficiale, aggiorna la scheda
> in `data/bandi_sicilia.json` (fonte + `ultimo_controllo` + `affidabilita_dati`), aggiungi un test se
> cambia il comportamento del motore, e rilancia demo e test. Aggiorna la sezione "Stato" di HANDOFF.md
> alla fine. Un commit per problema.
