# Metterlo online e farsi trovare

**Stato: online su https://bandi-mcp.vercel.app** (deploy del 18/09/2026, Vercel,
progetto `giospa97s-projects/bandi-mcp`). Repo: https://github.com/Ghiospa/bandi-mcp

Restano da fare: il dominio `bandi.prodgai.com`, e poi registry e directory. Le ultime
due **vanno fatte per ultime**: le schede del registry vengono crawlate e messe in cache,
e presentarsi con un catalogo magro brucia la prima impressione una volta sola.

---

## 1. Dov'è ora, e cosa cambia con Railway

Il deploy attuale è su Vercel, in modalità serverless. Il codice regge entrambe le
strade: gli interruttori `BANDI_STATELESS` e `BANDI_JSON_RESPONSE` sono spenti di
default e li accende solo `asgi.py`.

| | Vercel (oggi) | Railway/Render |
|---|---|---|
| Sessioni MCP | no, ogni richiesta è indipendente | sì |
| Risposte | JSON, niente streaming SSE | SSE |
| Latenza | cold start sulla prima chiamata | processo sempre caldo |
| Rate limit | per istanza, non globale | reale |
| Log d'uso | solo stdout, SQLite non sopravvive | SQLite su volume |

Finché il traffico è quello di tre commercialisti, la differenza non si sente. Quando
inizierà a sentirsi, `Dockerfile`, `railway.json` e `render.yaml` sono già nel repo:
servono un account e il login da browser, che sono passaggi tuoi.

### Rideploy su Vercel

```bash
vercel deploy --prod --yes
```

### Il dominio bandi.prodgai.com

Da pannello Vercel: Project → Settings → Domains → aggiungi `bandi.prodgai.com` e crea
il CNAME che ti indica sul DNS di `prodgai.com`. Non serve altro: `asgi.py` legge i
domini da `VERCEL_PROJECT_PRODUCTION_URL` e `VERCEL_URL` e li mette da solo negli host
ammessi, e `BANDI_BASE_URL` segue, quindi canonical e sitemap si aggiornano da soli.

### La variabile che rompe tutto se la sbagli

`BANDI_ALLOWED_HOSTS`. Senza, la libreria `mcp` **non** lascia passare tutto: vedendo un
bind locale applica da sola un allowlist di soli `127.0.0.1` e `localhost`, e ogni
richiesta al dominio pubblico riceve `421 Invalid Host header`. È esattamente l'errore
preso al primo deploy. Su Vercel la variabile si compone da sola; su Railway va
impostata a mano con il dominio del servizio.

### Verifica

```bash
curl -s https://bandi-mcp.vercel.app/health
```

Poi l'endpoint MCP vero:

```bash
curl -s -X POST https://bandi-mcp.vercel.app/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

## 2. Collegarlo a un agente

Una volta online, chiunque lo aggiunge senza registrarsi:

```bash
claude mcp add --transport http bandi https://bandi-mcp.vercel.app/mcp
```

In Claude Desktop: Impostazioni → Connettori → Aggiungi connettore personalizzato →
`https://bandi-mcp.vercel.app/mcp`.

Questo è il link da mettere ovunque: firma email, profilo LinkedIn, e nel messaggio ai
tre commercialisti. Per loro non c'è niente da installare.

---

## 3. Misurare

Su Vercel il log d'uso vive nei log della funzione (una riga JSON per chiamata, chiave
`uso`), perché il filesystem non sopravvive alla richiesta:

```bash
vercel logs bandi-mcp.vercel.app | grep '"uso"'
```

Su un host a processo, con SQLite su volume, il report è già pronto:

```bash
python scripts/report_uso.py --giorni 14
```

Chiamate al giorno, per tool, errori, e quante volte l'agente è rimasto con tre o più
campi mancanti. È il numero che dice se il test a due settimane è andato: non "quanti
hanno visto la pagina" ma "quante volte un agente ha chiesto davvero".

Controlla anche che il catalogo non invecchi — ogni pagina pubblica dichiara
`ultimo_controllo`, quindi una data vecchia è una promessa rotta:

```bash
python scripts/verifica_fonti.py --giorni 45
```

Esce con codice 1 se trova link morti o schede scadute: mettilo in CI settimanale.

---

## 4. Farsi trovare (solo quando il catalogo regge)

### 4.1 Registry ufficiale MCP

`server.json` è già nel repo, con namespace `com.prodgai/bandi`. Il namespace da
dominio richiede l'autenticazione DNS, e **il record va sul dominio apex
`prodgai.com`, non sul sottodominio** — è quello che determina il prefisso del nome.

```bash
brew install mcp-publisher
openssl genpkey -algorithm Ed25519 -out key.pem
PUBLIC_KEY="$(openssl pkey -in key.pem -pubout -outform DER | tail -c 32 | base64)"
echo "prodgai.com. IN TXT \"v=MCPv1; k=ed25519; p=${PUBLIC_KEY}\""
```

Crea quel record TXT sul DNS di `prodgai.com`, aspetta la propagazione, poi:

```bash
PRIVATE_KEY="$(openssl pkey -in key.pem -noout -text | grep -A3 "priv:" | tail -n +2 | tr -d ' :\n')"
mcp-publisher login dns --domain prodgai.com --private-key "${PRIVATE_KEY}"
mcp-publisher publish
```

`key.pem` è una chiave privata: tienila fuori dal repo (è già coperta da `.gitignore`).

Verifica:

```bash
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=com.prodgai/bandi"
```

`server.json` punta oggi a `https://bandi-mcp.vercel.app/mcp`: se attivi
`bandi.prodgai.com` prima di pubblicare, aggiorna quell'URL e rialza la `version`.

### 4.2 Directory

Il registry alimenta i client, le directory alimentano le persone che cercano. Sono
form manuali, uno diverso per ciascuna:

- **PulseMCP** — pulsemcp.com, la più curata sui server remoti
- **Glama** — glama.ai/mcp, chiede una riga di capability summary
- **Smithery** — smithery.ai
- **mcp.so** — la più grande per volume

Cosa serve a tutte: nome, descrizione, URL del repo, endpoint remoto, numero di tool
(nove) e una riga su cosa fa. Usa la descrizione di `server.json`, non riscriverla ogni
volta: la coerenza fra le schede conta.

### 4.3 Il canale con più volume

Non sono le directory: è l'agente che cerca sul web dentro una conversazione. Per
quello serve che `bandi.prodgai.com` sia indicizzato. Il sito lo serve già da solo
(`/`, una pagina per bando, `/llms.txt`, `/sitemap.xml`, `/robots.txt`,
`/catalogo.json`, dati strutturati `MonetaryGrant` su ogni scheda).

Da fare a mano dopo il deploy:

1. Google Search Console — verifica la proprietà e invia la sitemap
   (`https://bandi-mcp.vercel.app/sitemap.xml`, o quella del dominio definitivo)
2. Bing Webmaster Tools — stessa cosa, è quello che alimenta diversi motori usati dagli agenti
3. Qualche link in entrata da domini reali: ProdG, LinkedIn, un post che spiega il
   progetto. Senza nessun link il dominio resta invisibile per mesi

Un dominio `vercel.app` non si posiziona: la SEO vera parte quando il sito sta su
`bandi.prodgai.com`. Sulle misure nazionali competi con portali indicizzati da anni, e sulla SEO classica
perdi. La leva è un'altra: le tue pagine dichiarano fonte, data dell'ultimo controllo e
affidabilità del dato, e un modello che deve decidere di chi fidarsi trova qui quello
che altrove non c'è. Per questo `verifica_fonti.py` in CI non è igiene: è il prodotto.
