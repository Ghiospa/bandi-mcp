# Bandi MCP — guida per Claude Code

Server MCP agent-first per la finanza agevolata. Un consulente o un imprenditore non apre un portale:
il suo agente (Claude, ChatGPT) chiama i tool di questo server con il profilo dell'azienda e riceve
bandi compatibili, motivi strutturati, scadenze e uno scheletro di domanda.

Progetto di Giorgio Spadaro (ProdG AI Lab, Ragusa). Obiettivo: validare in 2 settimane con tre
commercialisti siciliani che usano già Claude. Vedi `HANDOFF.md` per stato e backlog.

## Stack e comandi

- Python 3.11+, Pydantic v2, `mcp>=2.0` (API `MCPServer`, non `FastMCP`; c'è un fallback per 1.x)
- `pip install -r requirements.txt`
- `python -m pytest -q` — 33 test, devono restare verdi dopo ogni modifica al motore o al catalogo
- `python scripts/demo.py` — tre profili tipo, stampa ranking e motivi; usalo per vedere l'effetto di una modifica
- `python -m bandi_mcp.server` — stdio; `--http` per streamable HTTP (host e porta da `BANDI_HOST`/`PORT`)
- `python scripts/genera_sito.py` — genera il sito in `./sito` per guardarlo prima del deploy
- `python scripts/report_uso.py` — chiamate al giorno per tool, dal log anonimo
- Test end-to-end sul protocollo: client `mcp.client.stdio.stdio_client` → `ClientSession` → `call_tool`
  (in mcp 2.x i campi del risultato sono `structured_content` e `is_error`, snake_case)

## Struttura

```
bandi_mcp/schema.py    modelli: ProfiloAzienda, Bando, Requisito, DateBando, EsitoAmmissibilita
bandi_mcp/matcher.py   motore deterministico: valuta(), classifica(), calcola_scadenza()
bandi_mcp/store.py     carica data/*.json (cache lru, ricarica())
bandi_mcp/server.py    definizione dei 9 tool + resource bandi://catalogo/sicilia
bandi_mcp/http_app.py  app HTTP pubblica: rate limit, host ammessi, /health, mount del sito
bandi_mcp/uso.py       log anonimo delle chiamate (middleware MCP) — mai dati di profilo
bandi_mcp/sito.py      pagine HTML generate dal catalogo (vedi "Il sito generato")
data/bandi_sicilia.json   catalogo (16 bandi al 18/09/2026)
Dockerfile, railway.json, render.yaml   deploy pubblico su bandi.prodgai.com
scripts/demo.py, scripts/genera_sito.py, scripts/report_uso.py, tests/, examples/
```

## Regole non negoziabili

1. **Il motore non usa LLM.** `matcher.py` è regole + dati. L'intelligenza sta nell'agente che chiama.
   Ogni punto del punteggio deve avere una riga in `fattori_punteggio`. Ogni esclusione un `MotivoEsclusione`
   con `campo`, `atteso`, `trovato`.
2. **Nessun dato inventato nel catalogo.** Ogni bando ha `fonti` (almeno un URL), `ultimo_controllo`,
   `affidabilita_dati`. Se un valore non è certo: campo `null` + nota + `affidabilita_dati: "da_verificare"`.
   Il motore penalizza da solo le schede da verificare.
3. **Campi mancanti, non errori.** Il profilo è tutto opzionale. Se un dato manca, finisce in `campi_mancanti`
   (e in `mancanti_bloccanti` se il requisito è bloccante), mai in un'eccezione.
4. **Output pensato per una macchina.** Dizionari JSON stabili, enum chiusi, date ISO, importi in EUR come
   numeri. Niente prosa nei tool tranne `sintesi` (una frase) e `istruzioni` in `bozza_domanda`.
5. **Errori verso l'agente con `ToolError`**, mai `ValueError` nudo: il messaggio deve dire cosa fare
   (es. elenco degli id validi, "chiama schema_profilo()").
6. **Nomi in italiano** per tool, campi, enum e commenti: è il lessico del dominio e degli utenti.
7. Il campo date del bando si chiama **`calendario`**, non `date` (shadowing di `datetime.date` in Pydantic).
8. Categorie di spesa e forme giuridiche sono `Literal` chiusi in `schema.py`: aggiungere lì, non stringhe libere.

## Convenzioni del catalogo

- `territori`: nomi regione con maiuscola (`"Sicilia"`), `["IT"]` tutta Italia, `["UE"]` Unione Europea
- `ateco_ammessi`: prefissi, sezione (`"C"`) o divisione (`"55"`); `null` = tutti
- `requisiti`: `tipo: "automatico"` con `campo_profilo`/`operatore`/`valore`, oppure `tipo: "dichiarativo"`
  (finisce in `verifiche_manuali`). Operatori: `== != >= <= < > in not_in between true false prefix_in`
- `calendario.ammissibilita_spese_da`: `presentazione_domanda | concessione | richiesta_preliminare |
  pec_domanda_banca | comunicazione_preventiva | <data ISO>`
- `regime_aiuti: "de_minimis"` attiva il controllo del plafond 300k su triennio mobile
- id: `ente-nome-anno` in kebab-case, es. `mimit-voucher-cloud-cybersecurity-2026`

## Flusso di lavoro

1. Leggi `HANDOFF.md` → scegli il task in cima al backlog non ancora fatto
2. Scrivi o aggiorna un test in `tests/` prima di toccare `matcher.py`
3. `python scripts/demo.py` per vedere il ranking sui tre profili; se cambia, spiegalo nel commit
4. `python -m pytest -q` verde
5. Aggiorna `HANDOFF.md` (sezione "Stato") e, se cambia l'interfaccia dei tool, il README

## Il sito generato

Esiste un sito pubblico (`bandi_mcp/sito.py`) e **non è una deroga aperta**: serve solo a farsi
trovare dagli agenti che cercano sul web invece di collegare un connettore. Il confine:

- Tutto il contenuto viene dal catalogo. Nessun testo scritto a mano dentro le pagine che non sia
  spiegazione del prodotto: se un'informazione non sta in `data/*.json`, non sta nemmeno nel sito
- Le pagine si rigenerano a ogni avvio del server: non possono divergere dal motore
- **Niente form, niente ricerca, niente filtri, niente account, niente JavaScript.** L'unica azione
  possibile da una pagina è collegare il server MCP
- Una pagina per bando più indice, `llms.txt`, `sitemap.xml`, `robots.txt`, `catalogo.json`. Nuovi tipi
  di pagina solo se derivano dal dato allo stesso modo
- Se ti trovi a voler aggiungere un filtro o un form, la risposta è un tool MCP, non una pagina

## Cosa NON fare

- Non aggiungere una UI applicativa: il prodotto è il server MCP e il dato, il sito è solo il dato
  reso leggibile (vedi sopra il confine)
- Non chiamare API LLM dal motore o dai tool
- Non pubblicare bandi ottenuti da scraping senza revisione umana (flag `affidabilita_dati`)
- Non rinominare tool o campi di output senza aggiornare README e test: sono un contratto per gli agenti
- Non far entrare dati di profilo nel log d'uso: `uso.py` registra solo tool, esito e conteggi, e
  c'è un test che fallisce se qualcuno aggiunge una colonna identificabile
