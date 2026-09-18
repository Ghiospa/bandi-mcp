"""
Genera il sito statico dal catalogo, per guardarlo prima che vada online.

    python scripts/genera_sito.py            # scrive in ./sito
    python scripts/genera_sito.py --dove /tmp/anteprima
    python -m http.server -d sito 8080       # poi aprilo su localhost:8080

In produzione non serve: `bandi_mcp/http_app.py` rigenera le pagine a ogni avvio.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bandi_mcp.sito import BASE_URL, genera  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dove", default="sito")
    args = ap.parse_args()
    cartella = Path(args.dove)
    n = genera(cartella)
    print(f"{n} file in {cartella}/ (URL pubblico atteso: {BASE_URL})")
    print(f"anteprima:  python -m http.server -d {cartella} 8080")


if __name__ == "__main__":
    main()
