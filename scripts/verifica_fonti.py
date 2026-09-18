"""
Controlla che le fonti del catalogo esistano ancora e che le schede non siano vecchie.

    python scripts/verifica_fonti.py                  # tutto il catalogo
    python scripts/verifica_fonti.py --giorni 30      # segnala le schede non controllate da 30 giorni
    python scripts/verifica_fonti.py --solo-date      # nessuna chiamata di rete
    python scripts/verifica_fonti.py --bando mimit-nuova-sabatini

Esce con codice 1 se trova un URL rotto o una scheda scaduta: è pensato anche per la CI.

La freschezza è l'unica cosa che ci distingue davvero da un portale: ogni pagina
pubblica dichiara `ultimo_controllo`, quindi una data vecchia è una promessa rotta.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bandi_mcp.store import carica_catalogo  # noqa: E402

AGENTE = "Mozilla/5.0 (compatible; bandi-mcp/0.1; +https://bandi.prodgai.com)"
TIMEOUT = 20


def controlla_url(url: str) -> tuple[str, int | str]:
    """Restituisce (url, codice). Una GET, non una HEAD: molti portali PA rifiutano le HEAD."""
    richiesta = urllib.request.Request(url, headers={"User-Agent": AGENTE}, method="GET")
    try:
        with urllib.request.urlopen(richiesta, timeout=TIMEOUT) as r:
            return url, r.status
    except urllib.error.HTTPError as e:
        return url, e.code
    except Exception as e:  # DNS, TLS, timeout
        return url, type(e).__name__


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--giorni", type=int, default=45, help="soglia di anzianità di ultimo_controllo")
    ap.add_argument("--solo-date", action="store_true", help="non interrogare la rete")
    ap.add_argument("--bando", help="controlla un solo id")
    args = ap.parse_args()

    bandi = carica_catalogo()
    if args.bando:
        bandi = [b for b in bandi if b.id == args.bando]
        if not bandi:
            sys.exit(f"Nessun bando con id '{args.bando}'")

    problemi = 0
    oggi = date.today()

    print(f"Anzianità delle schede (soglia {args.giorni} giorni)")
    scadute = [(b, (oggi - b.ultimo_controllo).days) for b in bandi if (oggi - b.ultimo_controllo).days > args.giorni]
    if scadute:
        for b, giorni in sorted(scadute, key=lambda x: -x[1]):
            print(f"  VECCHIA  {b.id}: controllata {giorni} giorni fa ({b.ultimo_controllo})")
        problemi += len(scadute)
    else:
        piu_vecchia = max((oggi - b.ultimo_controllo).days for b in bandi)
        print(f"  ok, la più vecchia è di {piu_vecchia} giorni")

    da_verificare = [b for b in bandi if b.affidabilita_dati == "da_verificare"]
    if da_verificare:
        print(f"\nSchede con dati da verificare ({len(da_verificare)}) — non un errore, ma è il debito da smaltire")
        for b in da_verificare:
            print(f"  {b.id}: {b.note[0] if b.note else 'nessuna nota'}")

    if args.solo_date:
        sys.exit(1 if problemi else 0)

    coppie = [(b, f.url) for b in bandi for f in b.fonti]
    print(f"\nFonti da controllare: {len(coppie)}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        esiti = dict(pool.map(controlla_url, {url for _, url in coppie}))

    rotte = 0
    for b, url in coppie:
        codice = esiti[url]
        if codice == 200:
            continue
        # 403 e 405: alcuni portali PA bloccano i client non browser. Non è un link morto.
        livello = "BLOCCATA" if codice in (403, 405, 406, 429) else "ROTTA"
        if livello == "ROTTA":
            rotte += 1
        print(f"  {livello:9s} {codice}  {b.id}\n            {url}")
    if rotte == 0:
        print("  nessun link morto")
    problemi += rotte

    print(f"\n{len(bandi)} schede, {len(coppie)} fonti, {rotte} link morti, {len(scadute)} schede scadute")
    sys.exit(1 if problemi else 0)


if __name__ == "__main__":
    main()
