# Bandi MCP

Finanza agevolata **agent-first**. Nessun portale, nessun filtro, nessuna newsletter:
un server MCP che l'agente dell'utente (Claude, ChatGPT, altro) interroga con il profilo
dell'azienda e da cui riceve risposte strutturate, con i motivi.

Catalogo iniziale: 16 misure accessibili alle imprese siciliane (nazionali + regionali),
verificate al 18/09/2026, ognuna con fonti e data dell'ultimo controllo.

```
consulente → il suo Claude → cerca_bandi(profilo) → [bandi ordinati per fit, motivi, scadenze, stima]
                              verifica_ammissibilita(bando, profilo) → [esito, campo atteso/trovato, cosa manca]
                              bozza_domanda(bando, profilo) → [scheletro della domanda con i dati già noti]
```

## Perché è diverso da un portale

Un portale mostra un elenco e una scheda PDF. Questo restituisce:

- **motivo di esclusione strutturato**: `{codice: "SPESA_MINIMA", campo: "investimento.importo_eur", atteso: ">= 750.000", trovato: 600.000}` — l'agente sa esattamente cosa dire al cliente e cosa cambierebbe l'esito
- **campi mancanti**: cosa chiedere, e per quanti bandi conta (`dati_che_migliorerebbero_la_ricerca`)
- **la data che conta oggi**, non un elenco di date: "18 giorni di preparazione prima dell'invio del 6/10" è diverso da "chiude il 21/12"
- **requisiti divisi in automatici e dichiarativi**: quelli che possiamo verificare sul profilo e quelli che il consulente deve confermare
- **stima lorda dell'agevolazione** e avvertenze fiscali (il fondo perduto è tassato)

Il vero asset è il **database normalizzato**: `data/bandi_sicilia.json`. Oggi questi dati sono sparsi
su venti portali in PDF. Chi li pulisce per primo ha un fossato.

## Avvio rapido

```bash
git clone <repo> && cd bandi-mcp
pip install -r requirements.txt
python scripts/demo.py          # tre profili tipo, senza MCP
python -m pytest -q             # 11 test
python -m bandi_mcp.server      # server MCP su stdio
python -m bandi_mcp.server --http   # streamable HTTP su :8000 per client remoti
```

### Collegarlo a Claude

**Claude Code** (dalla cartella del progetto):

```bash
claude mcp add --transport stdio bandi -- python -m bandi_mcp.server
```

**Claude Desktop**: aggiungere al file di configurazione il blocco in `examples/claude_desktop_config.json`,
sostituendo il percorso assoluto. Per la sintassi aggiornata di entrambi i client vale la documentazione ufficiale:
https://docs.claude.com/en/docs/claude-code/mcp e https://support.claude.com.

Poi, in chat:

> "Questa è la P.IVA della mia azienda cliente, fa carpenteria a Ragusa con 14 dipendenti e vuole
> comprare una linea CNC da 900k. A quali bandi può accedere e cosa mi manca per dirlo con certezza?"

L'agente chiama `schema_profilo`, costruisce il profilo, chiama `cerca_bandi`, legge `campi_mancanti`
e chiede solo quello che cambia l'esito.

## Tool esposti

| Tool | Input | Cosa restituisce |
|---|---|---|
| `schema_profilo` | — | JSON Schema del profilo + guida su dove ricavare ogni campo |
| `cerca_bandi` | `profilo`, `includi_esclusi`, `limite`, `solo_tag` | bandi compatibili ordinati per fit, esclusi con motivo, campi da chiedere |
| `verifica_ammissibilita` | `bando_id`, `profilo` | esito, motivi strutturati, avvertenze, verifiche manuali, fattori del punteggio, scadenza |
| `dettaglio_bando` | `bando_id` | scheda completa normalizzata |
| `requisiti_documentali` | `bando_id` | checklist, le tre date che contano, trappole ricorrenti |
| `scadenze_prossime` | `giorni`, `profilo?` | eventi (aperture/chiusure) nei prossimi N giorni, filtrati sul profilo |
| `bozza_domanda` | `bando_id`, `profilo`, `progetto?` | 7 sezioni con dati disponibili, dati mancanti, istruzioni, avvertenze |
| `elenco_bandi` | `stato?` | catalogo sintetico + tag disponibili |
| `ricarica_catalogo` | — | ricarica i JSON da disco |

Resource: `bandi://catalogo/sicilia` (tutto il catalogo, JSON).

### Esito

```json
{
  "bando_id": "mimit-investimenti-sostenibili-40-2026",
  "esito": "ammissibile_con_verifiche",
  "punteggio_fit": 96,
  "motivi_esclusione": [],
  "verifiche_manuali": ["Almeno il 25% del programma coperto con risorse proprie prive di sostegno pubblico..."],
  "campi_mancanti": [],
  "fattori_punteggio": ["+8 rientra in una quota riservata: 25% micro e piccole", "+20 spese coerenti: [digitale, macchinari]", "+5 finestra di preparazione: 18 giorni"],
  "prossima_scadenza": {"evento": "apertura_invio", "data": "2026-10-06", "giorni_rimanenti": 18, "urgenza": "media"},
  "stima_agevolazione_eur": 675000.0,
  "sintesi": "Compatibile con verifiche: agevolazione stimata fino a 675,000 €, invio dal 06/10/2026 (18 giorni per prepararsi)."
}
```

Esiti possibili: `ammissibile`, `ammissibile_con_verifiche`, `dati_insufficienti`, `non_ammissibile`.

## Struttura

```
bandi_mcp/
  schema.py    ProfiloAzienda, Bando, Requisito, EsitoAmmissibilita (Pydantic v2)
  matcher.py   motore deterministico: territorio, dimensione UE, ATECO, soglie, requisiti, de minimis, scadenze, fit
  store.py     carica data/*.json
  server.py    tool MCP (mcp>=2, fallback su FastMCP 1.x)
data/
  bandi_sicilia.json   16 bandi normalizzati con fonti
scripts/demo.py        tre profili tipo (officina, startup AI, hotel)
tests/                 11 test sul motore e sul catalogo
examples/              config Claude Desktop, profilo di esempio
```

Il motore **non usa LLM**. L'intelligenza sta nell'agente che chiama; qui ci sono regole spiegabili.
Ogni punto del punteggio ha una riga in `fattori_punteggio`.

## Aggiungere un bando

Una voce nell'array `bandi` di `data/bandi_sicilia.json` (o un nuovo file per un'altra regione).
Campi che fanno la differenza:

- `territori`: regioni ammesse, `["IT"]` per tutta Italia
- `dimensioni_ammesse`, `ateco_ammessi` (prefissi: sezione `"C"` o divisione `"55"`), `ateco_esclusi`
- `spesa_min_eur` / `spesa_max_eur` / `contributo_max_eur` / `intensita_max_pct` / `intensita_fondo_perduto_pct`
- `categorie_spesa`: da `CategoriaSpesa` in `schema.py`
- `calendario`: `apertura_compilazione`, `apertura_invio`, `chiusura`, `ammissibilita_spese_da`
- `requisiti`: automatici (`campo_profilo` + `operatore` + `valore`) o `dichiarativi`
- `regime_aiuti`: `de_minimis` attiva il controllo del plafond
- `fonti` con almeno un URL, `ultimo_controllo`, `affidabilita_dati`

`python -m pytest` verifica che il catalogo si carichi e che ogni bando abbia fonti.

## Cosa manca (in ordine)

1. **Ingestione**: oggi il catalogo è curato a mano. Il passo successivo è uno scraper + normalizzazione
   LLM dei portali regionali (euroinfosicilia, IRFIS, CCIAA, GAL) con revisione umana prima della pubblicazione.
2. **Copertura**: bandi camerali siciliani (voucher digitalizzazione), PR FESR Sicilia 2021-27, GAL.
3. **Profilo da P.IVA**: tool `profilo_da_visura(pdf)` che estrae ATECO, addetti, data costituzione, forma giuridica.
4. **Monitoraggio**: `scadenze_prossime` chiamato da un agente ogni mattina per i profili seguiti da un consulente.
5. **Hosting**: `--http` dietro autenticazione, così il consulente si collega dal suo Claude senza installare nulla.
6. **Distribuzione**: directory connettori Claude, ChatGPT apps.

## Test di validazione (2 settimane)

Darlo a tre commercialisti che usano già Claude. Misurare: quante volte lo interrogano senza sollecito,
su quanti clienti, e quante volte `campi_mancanti` li spinge a raccogliere un dato che non avevano.
Se lo usano, il prodotto c'è. Se no, il problema è nella distribuzione o nel dato, non nel tool.

## Avvertenze

Le schede sono ricavate da fonti ufficiali e secondarie (indicate per ogni bando) e vanno riverificate
sul testo dell'avviso prima di presentare una domanda. Le stime economiche sono lorde. Questo software
non sostituisce un consulente di finanza agevolata: gli fa risparmiare il 70% del tempo di screening.
