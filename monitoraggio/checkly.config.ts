import { defineConfig } from 'checkly'
import { Frequency } from 'checkly/constructs'

/**
 * Monitoraggio sintetico di bandi-mcp.
 *
 * Un check di uptime qui non basterebbe, e lo sappiamo per esperienza: al primo
 * deploy `/health` rispondeva 200 mentre `/mcp` dava 421 su ogni chiamata. Il
 * servizio risultava sano e non funzionava. Per questo i check parlano il
 * protocollo MCP invece di limitarsi a guardare lo status code della home.
 *
 * L'URL si cambia con BANDI_URL quando il servizio passa a bandi.prodgai.com:
 *
 *     BANDI_URL=https://bandi.prodgai.com npx checkly deploy
 */
export default defineConfig({
  projectName: 'Bandi MCP',
  logicalId: 'bandi-mcp',
  repoUrl: 'https://github.com/Ghiospa/bandi-mcp',
  checks: {
    frequency: Frequency.EVERY_30M,
    // Due sedi europee: gli utenti sono in Italia, e due bastano a distinguere
    // un servizio giù da una rete che fa i capricci.
    locations: ['eu-central-1', 'eu-west-1'],
    tags: ['bandi-mcp'],
    checkMatch: '**/checks/*.check.ts',
    runtimeId: '2025.04',
  },
  cli: {
    runLocation: 'eu-central-1',
  },
})
