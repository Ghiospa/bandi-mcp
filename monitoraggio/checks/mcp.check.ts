import { ApiCheck, AssertionBuilder, Frequency } from 'checkly/constructs'

const BASE = process.env.BANDI_URL ?? 'https://bandi-mcp.vercel.app'

const HEADERS_MCP = [
  { key: 'Content-Type', value: 'application/json' },
  { key: 'Accept', value: 'application/json, text/event-stream' },
]

/**
 * 1. L'handshake MCP.
 *
 * È il check che al primo deploy avrebbe suonato mentre /health diceva "ok":
 * la protezione DNS rebinding rispondeva 421 a ogni richiesta su /mcp.
 * Se questo fallisce, nessun agente al mondo riesce a collegarsi.
 */
new ApiCheck('mcp-initialize', {
  name: 'MCP: handshake',
  frequency: Frequency.EVERY_10M,
  maxResponseTime: 10000,
  degradedResponseTime: 4000,
  request: {
    url: `${BASE}/mcp`,
    method: 'POST',
    headers: HEADERS_MCP,
    bodyType: 'JSON',
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: {
        protocolVersion: '2025-06-18',
        capabilities: {},
        clientInfo: { name: 'checkly', version: '1' },
      },
    }),
    assertions: [
      AssertionBuilder.statusCode().equals(200),
      AssertionBuilder.jsonBody('$.result.serverInfo.name').equals('bandi-mcp'),
      // Le istruzioni sono quello che l'agente legge per capire come usarci:
      // se sparissero, il server sarebbe raggiungibile e inutilizzabile.
      AssertionBuilder.jsonBody('$.result.instructions').notEmpty(),
    ],
  },
})

/**
 * 2. I nove tool sono ancora esposti.
 *
 * I nomi dei tool sono un contratto con gli agenti già collegati: rinominarne
 * uno per sbaglio rompe le integrazioni senza che niente vada in errore.
 */
new ApiCheck('mcp-tools-list', {
  name: 'MCP: i tool esposti',
  frequency: Frequency.EVERY_30M,
  request: {
    url: `${BASE}/mcp`,
    method: 'POST',
    headers: HEADERS_MCP,
    bodyType: 'JSON',
    body: JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/list' }),
    assertions: [
      AssertionBuilder.statusCode().equals(200),
      AssertionBuilder.textBody().contains('cerca_bandi'),
      AssertionBuilder.textBody().contains('verifica_ammissibilita'),
      AssertionBuilder.textBody().contains('bozza_domanda'),
    ],
  },
})

/**
 * 3. Il motore risponde davvero, su un profilo vero.
 *
 * Officina meccanica di Ragusa, lo stesso profilo della demo. Non asserisce
 * quali bandi escono — il ranking cambia ogni volta che il catalogo migliora,
 * e un check che si rompe a ogni miglioramento viene silenziato dopo due
 * settimane. Asserisce che il catalogo si sia caricato e che qualcosa esca:
 * prende il caso in cui un JSON malformato lascia il server in piedi e vuoto.
 */
new ApiCheck('mcp-cerca-bandi', {
  name: 'MCP: cerca_bandi su un profilo reale',
  frequency: Frequency.EVERY_30M,
  maxResponseTime: 15000,
  request: {
    url: `${BASE}/mcp`,
    method: 'POST',
    headers: HEADERS_MCP,
    bodyType: 'JSON',
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 3,
      method: 'tools/call',
      params: {
        name: 'cerca_bandi',
        arguments: {
          profilo: {
            ateco: '25.62',
            regione: 'Sicilia',
            addetti_ula: 14,
            fatturato_ultimo_eur: 2100000,
            investimento: { importo_eur: 900000, categorie: ['macchinari', 'digitale'] },
          },
          limite: 3,
        },
      },
    }),
    assertions: [
      AssertionBuilder.statusCode().equals(200),
      AssertionBuilder.jsonBody('$.result.isError').equals(false),
      AssertionBuilder.jsonBody('$.result.structuredContent.totale_catalogo').greaterThan(25),
      AssertionBuilder.jsonBody('$.result.structuredContent.compatibili[0].bando_id').notEmpty(),
    ],
  },
})

/**
 * 4. Gli errori applicativi arrivano ancora come tali.
 *
 * Un id inesistente deve tornare isError con l'elenco degli id validi, non un
 * 500 e non un successo vuoto. È il contratto che permette a un agente di
 * correggersi da solo invece di riferire "errore" all'utente.
 */
new ApiCheck('mcp-errore-strutturato', {
  name: 'MCP: un id sbagliato torna un errore utile',
  frequency: Frequency.EVERY_1H,
  request: {
    url: `${BASE}/mcp`,
    method: 'POST',
    headers: HEADERS_MCP,
    bodyType: 'JSON',
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 4,
      method: 'tools/call',
      params: { name: 'dettaglio_bando', arguments: { bando_id: 'questo-non-esiste' } },
    }),
    assertions: [
      AssertionBuilder.statusCode().equals(200),
      AssertionBuilder.jsonBody('$.result.isError').equals(true),
      AssertionBuilder.textBody().contains('ID disponibili'),
    ],
  },
})
