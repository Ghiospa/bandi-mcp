# Monitoraggio

Check sintetici [Checkly](https://www.checklyhq.com), definiti come codice e versionati
insieme al servizio che controllano.

## Perché non basta un check di uptime

Al primo deploy `/health` rispondeva `200` mentre `/mcp` restituiva `421` a ogni chiamata:
la libreria `mcp`, non ricevendo l'host di bind, applicava da sola un allowlist di soli
host locali. Un monitor sulla home avrebbe detto che il servizio stava benissimo mentre
nessun agente riusciva a collegarsi.

Per questo i check parlano il protocollo invece di guardare uno status code.

## Cosa controlla

| Check | Frequenza | Prende |
|---|---|---|
| MCP: handshake | 10 min | il servizio irraggiungibile *per un agente*, anche se la home risponde |
| MCP: i tool esposti | 30 min | un tool rinominato per sbaglio: i nomi sono un contratto con chi è già collegato |
| MCP: cerca_bandi su un profilo reale | 30 min | il catalogo che non si carica e lascia il server in piedi e vuoto |
| MCP: un id sbagliato torna un errore utile | 1 h | gli errori che smettono di essere strutturati e l'agente non sa più correggersi |
| Dato: il catalogo non è invecchiato | 1 h | `ultimo_controllo` oltre 45 giorni — un servizio che risponde e mente |
| Sito: llms.txt e indice | 1 h | il mount statico che si rompe in silenzio senza toccare `/mcp` |
| CI: verifica delle fonti | 7 giorni | il job settimanale che smette di partire invece di fallire |

Il check sulla freschezza del dato è il meno ovvio e il più importante: su quello si regge
l'unico motivo per cui un agente dovrebbe fidarsi di noi invece del primo portale che
trova, e un catalogo fermo da due mesi è un guasto anche se risponde `200` a tutto.

Nessun check asserisce *quali* bandi escono da `cerca_bandi`: il ranking cambia ogni volta
che il catalogo migliora, e un check che si rompe a ogni miglioramento viene silenziato
dopo due settimane.

## Usarlo

```bash
cd monitoraggio
npm install
npx checkly login          # serve un account, il piano gratuito basta
npx checkly test           # esegue i check una volta, senza crearli
npx checkly deploy         # li crea e li mette in esecuzione
```

Quando il servizio passerà a `bandi.prodgai.com`:

```bash
BANDI_URL=https://bandi.prodgai.com npx checkly deploy
```

Gli alert non sono definiti qui: impostali dal pannello (email, Slack, Telegram) oppure
aggiungi un `EmailAlertChannel` in un file di check. Non ho messo indirizzi nel repo.

Dopo il primo deploy, copia l'URL del monitor «CI: verifica delle fonti del catalogo» nel
segreto GitHub `CHECKLY_HEARTBEAT_URL`, che `.github/workflows/verifica-fonti.yml` usa per
il ping settimanale.

## Verificato

Le asserzioni sono state provate contro la produzione prima del commit: 24 su 24 verdi.
Il typecheck (`npx tsc --noEmit`) passa su checkly 9.5.0. Quello che **non** ho potuto
eseguire è `checkly test`, che richiede un account.
