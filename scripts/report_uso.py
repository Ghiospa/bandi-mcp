"""
Cosa è stato usato, quanto, e dove l'agente è rimasto senza dati.

    python scripts/report_uso.py                 # ultimi 14 giorni
    python scripts/report_uso.py --giorni 30
    python scripts/report_uso.py --db /dati/uso.sqlite3

Legge il log anonimo scritto da `bandi_mcp/uso.py`. Nessun dato di profilo: solo
tool, giorno, esito e due conteggi.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path


def apri(db: Path) -> sqlite3.Connection:
    if not db.exists():
        sys.exit(f"Nessun log in {db}. Il server non è mai stato chiamato, oppure BANDI_LOG_DB punta altrove.")
    return sqlite3.connect(db)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("BANDI_LOG_DB", "data/uso.sqlite3"))
    ap.add_argument("--giorni", type=int, default=14)
    args = ap.parse_args()

    conn = apri(Path(args.db))
    da = (date.today() - timedelta(days=args.giorni)).isoformat()

    totale, errori = conn.execute(
        "SELECT COUNT(*), SUM(esito = 'errore') FROM chiamate WHERE ts >= ?", (da,)
    ).fetchone()
    if not totale:
        print(f"Nessuna chiamata negli ultimi {args.giorni} giorni.")
        return

    giorni_attivi = conn.execute("SELECT COUNT(DISTINCT substr(ts, 1, 10)) FROM chiamate WHERE ts >= ?", (da,)).fetchone()[0]
    print(f"Ultimi {args.giorni} giorni: {totale} chiamate in {giorni_attivi} giorni attivi "
          f"({totale / max(giorni_attivi, 1):.1f} al giorno), {errori or 0} errori\n")

    print("Per tool")
    print(f"  {'tool':28s} {'chiamate':>8s} {'errori':>7s} {'ms medi':>8s} {'campi mancanti medi':>20s}")
    for tool, n, err, ms, campi in conn.execute(
        "SELECT tool, COUNT(*), SUM(esito = 'errore'), AVG(durata_ms), AVG(campi_mancanti)"
        " FROM chiamate WHERE ts >= ? GROUP BY tool ORDER BY COUNT(*) DESC",
        (da,),
    ):
        campi_txt = f"{campi:.1f}" if campi is not None else "-"
        print(f"  {tool:28s} {n:8d} {err or 0:7d} {ms or 0:8.0f} {campi_txt:>20s}")

    print("\nPer giorno")
    for giorno, n, err in conn.execute(
        "SELECT substr(ts, 1, 10), COUNT(*), SUM(esito = 'errore') FROM chiamate WHERE ts >= ?"
        " GROUP BY 1 ORDER BY 1",
        (da,),
    ):
        barra = "█" * min(60, n)
        print(f"  {giorno}  {n:5d} {barra}" + (f"  ({err} errori)" if err else ""))

    senza_dati = conn.execute(
        "SELECT COUNT(*) FROM chiamate WHERE ts >= ? AND campi_mancanti >= 3", (da,)
    ).fetchone()[0]
    if senza_dati:
        print(f"\n{senza_dati} chiamate con 3+ campi mancanti: sono i casi in cui l'agente non aveva\n"
              "abbastanza profilo per una risposta utile. Se il numero è alto, il problema è\n"
              "schema_profilo o le istruzioni, non il motore.")


if __name__ == "__main__":
    main()
