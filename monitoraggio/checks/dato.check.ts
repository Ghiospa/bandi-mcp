import { ApiCheck, AssertionBuilder, Frequency, HeartbeatMonitor } from 'checkly/constructs'

const BASE = process.env.BANDI_URL ?? 'https://bandi-mcp.vercel.app'

/**
 * 1. La freschezza del catalogo, trattata come un guasto.
 *
 * È il check meno ovvio e il più importante. Ogni pagina pubblica dichiara
 * `ultimo_controllo`, e su questo si regge l'unico motivo per cui un agente
 * dovrebbe fidarsi di noi invece che del primo portale che trova. Un catalogo
 * fermo da due mesi è un servizio rotto anche se risponde 200 a tutto, e va
 * svegliato qualcuno esattamente come per un server giù.
 *
 * La soglia è 45 giorni, la stessa di `scripts/verifica_fonti.py`: se la
 * cambi lì, cambiala qui.
 */
new ApiCheck('dato-freschezza-catalogo', {
  name: 'Dato: il catalogo non è invecchiato',
  frequency: Frequency.EVERY_1H,
  request: {
    url: `${BASE}/health`,
    method: 'GET',
    assertions: [
      AssertionBuilder.statusCode().equals(200),
      AssertionBuilder.jsonBody('$.stato').equals('ok'),
      AssertionBuilder.jsonBody('$.giorni_dall_ultimo_controllo').lessThan(45),
      // Un catalogo che si carica ma resta vuoto risponderebbe comunque "ok".
      AssertionBuilder.jsonBody('$.bandi').greaterThan(25),
      AssertionBuilder.jsonBody('$.aperti').greaterThan(0),
    ],
  },
})

/**
 * 2. Il canale di traffico verso gli agenti.
 *
 * Il sito e `llms.txt` sono l'unico modo in cui ci trova un agente che cerca
 * sul web invece di collegare un connettore. Sono serviti dallo stesso
 * processo dell'endpoint MCP, con un mount statico montato dopo /mcp: è
 * esattamente il tipo di cosa che si rompe in silenzio quando si tocca il
 * routing, senza che nessuna chiamata MCP se ne accorga.
 */
new ApiCheck('sito-llms-txt', {
  name: 'Sito: llms.txt manda ancora all\'endpoint',
  frequency: Frequency.EVERY_1H,
  request: {
    url: `${BASE}/llms.txt`,
    method: 'GET',
    assertions: [
      AssertionBuilder.statusCode().equals(200),
      AssertionBuilder.textBody().contains('/mcp'),
      AssertionBuilder.textBody().contains('cerca_bandi'),
    ],
  },
})

new ApiCheck('sito-indice', {
  name: 'Sito: indice del catalogo',
  frequency: Frequency.EVERY_1H,
  request: {
    url: `${BASE}/`,
    method: 'GET',
    assertions: [
      AssertionBuilder.statusCode().equals(200),
      AssertionBuilder.textBody().contains('Bandi MCP'),
      // Se il mount statico saltasse, questo tornerebbe 404 mentre /mcp sta bene.
      AssertionBuilder.textBody().contains('/bandi/'),
    ],
  },
})

/**
 * 3. Il controllo delle fonti sta ancora girando.
 *
 * `scripts/verifica_fonti.py` in CI settimanale è quello che tiene onesta la
 * freschezza. Ma un job che smette di partire non fallisce: sparisce. Il
 * heartbeat rovescia la logica — se nessuno lo chiama entro otto giorni,
 * suona.
 *
 * Il ping lo fa il job alla fine, con l'URL che Checkly assegna a questo
 * monitor dopo il primo deploy:
 *
 *     curl -fsS "$CHECKLY_HEARTBEAT_URL"
 */
new HeartbeatMonitor('verifica-fonti-settimanale', {
  name: 'CI: verifica delle fonti del catalogo',
  activated: true,
  period: 7,
  periodUnit: 'days',
  grace: 1,
  graceUnit: 'days',
})
