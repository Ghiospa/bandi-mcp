# Metterlo online e farsi trovare

Runbook in quattro fasi. Le fasi 1 e 2 le puoi fare oggi. La fase 4 — registry e
directory — **va fatta per ultima**, quando il catalogo vale la pena: le schede del
registry vengono crawlate e messe in cache, e presentarsi con un catalogo magro brucia
la prima impressione una volta sola.

Quello che serve a te e che io non posso fare: gli account (Railway o Render), il DNS
di `prodgai.com`, e i form di submission delle directory.

---

## 1. Deploy su bandi.prodgai.com

Il repo ha già `Dockerfile`, `railway.json` e `render.yaml` con healthcheck e volume.

**Railway**

```bash
railway login && railway init && railway up
```

Poi da pannello: Settings → Networking → Custom Domain → `bandi.prodgai.com`, e crea
il CNAME che ti indica. Variabili da impostare:

| Variabile | Valore | Perché |
|---|---|---|
| `BANDI_HOST` | `0.0.0.0` | già nel Dockerfile, ma esplicito non fa male |
| `BANDI_ALLOWED_HOSTS` | `bandi.prodgai.com` | **senza questa la protezione DNS rebinding resta spenta** |
| `BANDI_BASE_URL` | `https://bandi.prodgai.com` | canonical, sitemap e llms.txt |
| `BANDI_RATE_LIMIT` | `60` | richieste al minuto per IP |
| `BANDI_LOG_DB` | `/dati/uso.sqlite3` | su volume, altrimenti il log sparisce a ogni deploy |

Monta un volume su `/dati`, altrimenti resta solo la copia del log su stdout.

**Render**: `render.yaml` è già pronto, basta collegare il repo e confermare.

**Verifica** (sostituisci il dominio quando il DNS ha propagato):

```bash
curl -s https://bandi.prodgai.com/health
```

Deve rispondere `{"stato":"ok","bandi":26,...}`. Poi prova l'endpoint MCP vero:

```bash
curl -s -X POST https://bandi.prodgai.com/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

Se torna `406` o `400` controlla gli header. Se torna `421` o un errore di host,
`BANDI_ALLOWED_HOSTS` non corrisponde al dominio.

**Nota onesta**: il `Dockerfile` non è mai stato costruito, su questa macchina Docker
non era disponibile. Il primo `build` potrebbe chiedere una correzione banale.

---

## 2. Collegarlo a un agente

Una volta online, chiunque lo aggiunge senza registrarsi:

```bash
claude mcp add --transport http bandi https://bandi.prodgai.com/mcp
```

In Claude Desktop: Impostazioni → Connettori → Aggiungi connettore personalizzato →
`https://bandi.prodgai.com/mcp`.

Questo è il link da mettere ovunque: firma email, profilo LinkedIn, e nel messaggio ai
tre commercialisti. Per loro non c'è niente da installare.

---

## 3. Misurare

```bash
railway run python scripts/report_uso.py --giorni 14
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

Quando esiste un repo GitHub pubblico, aggiungi a `server.json` il campo `repository`:
le directory lo usano per mostrare stelle e attività, e un server senza repo visibile
viene guardato con sospetto.

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

1. Google Search Console — verifica la proprietà e invia `https://bandi.prodgai.com/sitemap.xml`
2. Bing Webmaster Tools — stessa cosa, è quello che alimenta diversi motori usati dagli agenti
3. Qualche link in entrata da domini reali: ProdG, LinkedIn, un post che spiega il
   progetto. Senza nessun link il dominio resta invisibile per mesi

Sulle misure nazionali competi con portali indicizzati da anni, e sulla SEO classica
perdi. La leva è un'altra: le tue pagine dichiarano fonte, data dell'ultimo controllo e
affidabilità del dato, e un modello che deve decidere di chi fidarsi trova qui quello
che altrove non c'è. Per questo `verifica_fonti.py` in CI non è igiene: è il prodotto.
