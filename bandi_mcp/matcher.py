"""
Motore di ammissibilità. Deterministico, spiegabile, senza LLM:
l'intelligenza sta nell'agente che chiama, qui ci sono le regole.

Ogni esito porta con sé PERCHÉ: motivi strutturati, campi mancanti,
verifiche da fare a mano. Un agente può leggerli e agire; un portale no.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from .schema import (
    Bando,
    EsitoAmmissibilita,
    MotivoEsclusione,
    ProfiloAzienda,
    Requisito,
    Scadenza,
)

REGIONI_MEZZOGIORNO_7 = ["Basilicata", "Calabria", "Campania", "Molise", "Puglia", "Sardegna", "Sicilia"]
REGIONI_MEZZOGIORNO_8 = REGIONI_MEZZOGIORNO_7 + ["Abruzzo"]
PLAFOND_DE_MINIMIS_EUR = 300_000.0  # Reg. UE 2023/2831, triennio mobile


# --------------------------------------------------------------------------- #
# Utilità
# --------------------------------------------------------------------------- #
def _get(obj: Any, path: str) -> Any:
    """Legge 'investimento.importo_eur' da un modello Pydantic o dict."""
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return cur


def _valuta_operatore(op: str, trovato: Any, atteso: Any) -> bool:
    if op == "==":
        return trovato == atteso
    if op == "!=":
        return trovato != atteso
    if op == ">=":
        return trovato >= atteso
    if op == "<=":
        return trovato <= atteso
    if op == ">":
        return trovato > atteso
    if op == "<":
        return trovato < atteso
    if op == "in":
        return trovato in atteso
    if op == "not_in":
        return trovato not in atteso
    if op == "between":
        lo, hi = atteso
        return (lo is None or trovato >= lo) and (hi is None or trovato <= hi)
    if op == "true":
        return bool(trovato) is True
    if op == "false":
        return bool(trovato) is False
    if op == "prefix_in":
        s = str(trovato).upper()
        return any(s.startswith(str(p).upper()) for p in atteso)
    raise ValueError(f"operatore sconosciuto: {op}")


def calcola_scadenza(bando: Bando, oggi: Optional[date] = None) -> Scadenza:
    """La data che conta ADESSO per questo bando, non un elenco di date."""
    oggi = oggi or date.today()
    d = bando.calendario

    def urg(giorni: int) -> str:
        if giorni <= 14:
            return "alta"
        if giorni <= 45:
            return "media"
        return "bassa"

    if bando.stato == "in_apertura":
        if d.apertura_compilazione and d.apertura_compilazione > oggi:
            g = (d.apertura_compilazione - oggi).days
            return Scadenza(evento="apertura_compilazione", data=d.apertura_compilazione, giorni_rimanenti=g, urgenza=urg(g))
        if d.apertura_invio and d.apertura_invio > oggi:
            g = (d.apertura_invio - oggi).days
            return Scadenza(evento="apertura_invio", data=d.apertura_invio, giorni_rimanenti=g, urgenza=urg(g))
        return Scadenza(evento="in_apertura", data=None, giorni_rimanenti=None, urgenza="media")

    # compilazione già aperta ma invio nel futuro: la finestra di preparazione è la scadenza vera
    if d.apertura_invio and d.apertura_invio > oggi:
        g = (d.apertura_invio - oggi).days
        return Scadenza(evento="apertura_invio", data=d.apertura_invio, giorni_rimanenti=g, urgenza=urg(g))

    if d.chiusura:
        g = (d.chiusura - oggi).days
        if g < 0:
            return Scadenza(evento="chiusura", data=d.chiusura, giorni_rimanenti=g, urgenza="nessuna")
        return Scadenza(evento="chiusura", data=d.chiusura, giorni_rimanenti=g, urgenza=urg(g))

    return Scadenza(evento="sportello_continuo", data=None, giorni_rimanenti=None, urgenza="bassa")


# --------------------------------------------------------------------------- #
# Valutazione
# --------------------------------------------------------------------------- #
def valuta(bando: Bando, profilo: ProfiloAzienda, oggi: Optional[date] = None) -> EsitoAmmissibilita:
    oggi = oggi or date.today()
    esclusioni: list[MotivoEsclusione] = []
    avvertenze: list[MotivoEsclusione] = []
    verifiche: list[str] = []
    mancanti: list[str] = []
    fattori: list[str] = []
    punteggio = 60  # base: un bando aperto e compatibile parte da qui

    # --- stato ------------------------------------------------------------ #
    scad = calcola_scadenza(bando, oggi)
    if bando.stato == "chiuso" or (scad.evento == "chiusura" and scad.giorni_rimanenti is not None and scad.giorni_rimanenti < 0):
        esclusioni.append(MotivoEsclusione(codice="STATO_CHIUSO", descrizione="Il bando è chiuso", campo="stato", trovato=bando.stato))
    elif bando.stato == "sospeso":
        esclusioni.append(MotivoEsclusione(codice="STATO_SOSPESO", descrizione="Sportello sospeso", campo="stato", trovato=bando.stato))

    # --- territorio ------------------------------------------------------- #
    if "IT" not in bando.territori and "UE" not in bando.territori:
        if profilo.regione is None:
            mancanti.append("regione")
        elif profilo.regione not in bando.territori:
            esclusioni.append(
                MotivoEsclusione(
                    codice="TERRITORIO", descrizione="Regione non ammessa", campo="regione",
                    atteso=bando.territori, trovato=profilo.regione,
                )
            )

    # --- dimensione ------------------------------------------------------- #
    dim = profilo.dimensione
    if dim is None:
        mancanti.append("addetti_ula (serve per la dimensione d'impresa)")
    elif dim not in bando.dimensioni_ammesse:
        esclusioni.append(
            MotivoEsclusione(
                codice="DIMENSIONE", descrizione="Dimensione d'impresa non ammessa", campo="dimensione",
                atteso=bando.dimensioni_ammesse, trovato=dim,
            )
        )
    else:
        if profilo.fatturato_ultimo_eur is None and profilo.totale_bilancio_eur is None:
            avvertenze.append(
                MotivoEsclusione(
                    codice="DIMENSIONE_DA_CONFERMARE", bloccante=False,
                    descrizione="Dimensione stimata dai soli addetti: confermare con fatturato o totale di bilancio",
                    campo="fatturato_ultimo_eur",
                )
            )
        # riserve dedicate alle imprese più piccole
        for r in bando.riserve:
            rl = r.lower()
            if ("micro" in rl or "piccol" in rl) and dim in ("micro", "piccola"):
                punteggio += 8
                fattori.append(f"+8 rientra in una quota riservata: {r}")

    # --- beneficiario ----------------------------------------------------- #
    if profilo.forma_giuridica == "libero_professionista" and "libero_professionista" not in bando.beneficiari:
        esclusioni.append(
            MotivoEsclusione(
                codice="BENEFICIARIO", descrizione="I liberi professionisti non sono ammessi", campo="forma_giuridica",
                atteso=bando.beneficiari, trovato=profilo.forma_giuridica,
            )
        )
    if profilo.forma_giuridica in ("ets",) and "ets" not in bando.beneficiari and "impresa_sociale" not in bando.beneficiari:
        esclusioni.append(
            MotivoEsclusione(
                codice="BENEFICIARIO", descrizione="Enti del terzo settore non ammessi", campo="forma_giuridica",
                atteso=bando.beneficiari, trovato=profilo.forma_giuridica,
            )
        )
    if "startup_innovativa" in bando.beneficiari and len(bando.beneficiari) == 1:
        if profilo.startup_innovativa is None:
            mancanti.append("startup_innovativa")
        elif not profilo.startup_innovativa:
            esclusioni.append(
                MotivoEsclusione(
                    codice="BENEFICIARIO", descrizione="Riservato a startup innovative iscritte alla sezione speciale",
                    campo="startup_innovativa", atteso=True, trovato=False,
                )
            )

    # --- ATECO ------------------------------------------------------------ #
    if bando.ateco_ammessi is not None:
        if profilo.ateco is None:
            mancanti.append("ateco")
        else:
            code = profilo.ateco.strip().upper()
            sez = profilo.sezione_ateco or ""
            ok = any(code.startswith(p.upper()) or sez == p.upper() for p in bando.ateco_ammessi)
            if not ok:
                esclusioni.append(
                    MotivoEsclusione(
                        codice="ATECO", descrizione="Settore non ammesso", campo="ateco",
                        atteso=bando.ateco_ammessi, trovato=profilo.ateco,
                    )
                )
    if bando.ateco_esclusi and profilo.ateco:
        code = profilo.ateco.strip().upper()
        sez = profilo.sezione_ateco or ""
        if any(code.startswith(p.upper()) or sez == p.upper() for p in bando.ateco_esclusi):
            esclusioni.append(
                MotivoEsclusione(
                    codice="ATECO_ESCLUSO", descrizione="Settore espressamente escluso", campo="ateco",
                    atteso=f"non in {bando.ateco_esclusi}", trovato=profilo.ateco,
                )
            )

    # --- importo investimento --------------------------------------------- #
    imp = profilo.investimento.importo_eur
    if bando.spesa_min_eur is not None or bando.spesa_max_eur is not None:
        if imp is None:
            mancanti.append("investimento.importo_eur")
        else:
            if bando.spesa_min_eur is not None and imp < bando.spesa_min_eur:
                esclusioni.append(
                    MotivoEsclusione(
                        codice="SPESA_MINIMA", descrizione="Investimento sotto la soglia minima", campo="investimento.importo_eur",
                        atteso=f">= {bando.spesa_min_eur:,.0f}", trovato=imp,
                    )
                )
            if bando.spesa_max_eur is not None and imp > bando.spesa_max_eur:
                avvertenze.append(
                    MotivoEsclusione(
                        codice="SPESA_MASSIMA", bloccante=False, descrizione="Investimento oltre il massimale: la parte eccedente resta a carico",
                        campo="investimento.importo_eur", atteso=f"<= {bando.spesa_max_eur:,.0f}", trovato=imp,
                    )
                )

    # --- coerenza categorie di spesa -------------------------------------- #
    cat_prof = set(profilo.investimento.categorie)
    cat_bando = set(bando.categorie_spesa)
    if cat_prof and cat_bando:
        overlap = cat_prof & cat_bando
        if not overlap:
            avvertenze.append(
                MotivoEsclusione(
                    codice="SPESE_NON_COERENTI", bloccante=False,
                    descrizione="Nessuna categoria di spesa prevista rientra tra quelle ammissibili",
                    campo="investimento.categorie", atteso=sorted(cat_bando), trovato=sorted(cat_prof),
                )
            )
            punteggio -= 25
            fattori.append("-25 spese previste fuori perimetro del bando")
        else:
            bonus = min(20, 10 * len(overlap))
            punteggio += bonus
            fattori.append(f"+{bonus} spese coerenti: {sorted(overlap)}")
    elif not cat_prof:
        mancanti.append("investimento.categorie")

    # --- de minimis ------------------------------------------------------- #
    if bando.regime_aiuti == "de_minimis":
        if profilo.de_minimis_ricevuti_36_mesi_eur is None:
            verifiche.append("Verificare il plafond de minimis residuo sul Registro Nazionale Aiuti (300.000 € su triennio mobile)")
        else:
            residuo = PLAFOND_DE_MINIMIS_EUR - profilo.de_minimis_ricevuti_36_mesi_eur
            if residuo <= 0:
                esclusioni.append(
                    MotivoEsclusione(
                        codice="DE_MINIMIS_ESAURITO", descrizione="Plafond de minimis esaurito", campo="de_minimis_ricevuti_36_mesi_eur",
                        atteso=f"< {PLAFOND_DE_MINIMIS_EUR:,.0f}", trovato=profilo.de_minimis_ricevuti_36_mesi_eur,
                    )
                )
            elif bando.contributo_max_eur and residuo < bando.contributo_max_eur:
                avvertenze.append(
                    MotivoEsclusione(
                        codice="DE_MINIMIS_LIMITANTE", bloccante=False,
                        descrizione=f"Il plafond residuo ({residuo:,.0f} €) è inferiore al contributo massimo: l'aiuto sarà ridotto",
                        campo="de_minimis_ricevuti_36_mesi_eur",
                    )
                )

    # --- requisiti strutturati del bando ---------------------------------- #
    mancanti_bloccanti: list[str] = []
    for req in bando.requisiti:
        _valuta_requisito(req, profilo, esclusioni, avvertenze, verifiche, mancanti, mancanti_bloccanti)
    for campo in mancanti_bloccanti:
        punteggio -= 25
        fattori.append(f"-25 requisito bloccante non verificabile: manca '{campo}'")

    # --- tempi ------------------------------------------------------------ #
    if scad.urgenza == "alta" and scad.evento == "chiusura":
        if bando.procedura in ("valutativa", "graduatoria"):
            punteggio -= 15
            fattori.append("-15 chiude entro 14 giorni con procedura valutativa: poco tempo per un progetto competitivo")
        else:
            punteggio -= 5
            fattori.append("-5 chiude entro 14 giorni")
    if scad.evento == "apertura_invio" and scad.giorni_rimanenti is not None:
        punteggio += 5
        fattori.append(f"+5 finestra di preparazione aperta: {scad.giorni_rimanenti} giorni per arrivare pronti all'invio")
    if bando.stato == "sportello_continuo":
        punteggio += 3
        fattori.append("+3 sportello continuo, nessuna corsa")

    # --- intensità ---------------------------------------------------------- #
    if bando.intensita_fondo_perduto_pct:
        b = min(10, int(bando.intensita_fondo_perduto_pct / 10))
        punteggio += b
        fattori.append(f"+{b} quota a fondo perduto fino al {bando.intensita_fondo_perduto_pct:.0f}%")

    # --- spese già avviate? ---------------------------------------------- #
    avvio = profilo.investimento.avvio_previsto
    if avvio and bando.calendario.ammissibilita_spese_da == "presentazione_domanda":
        if scad.evento == "apertura_invio" and scad.data and avvio < scad.data:
            avvertenze.append(
                MotivoEsclusione(
                    codice="SPESE_ANTICIPATE", bloccante=False,
                    descrizione="Vuole spendere prima che si possa inviare la domanda: quelle spese non sarebbero ammissibili",
                    campo="investimento.avvio_previsto", atteso=f">= {scad.data}", trovato=avvio,
                )
            )
            punteggio -= 10
            fattori.append("-10 rischio spese anticipate non ammissibili")

    # --- base di calcolo dell'agevolazione -------------------------------- #
    if bando.base_calcolo == "massimali_specifici":
        verifiche.append(
            "L'incentivo non è una percentuale della spesa totale: dipende dai massimali di spesa "
            "specifica per tipologia di intervento (€/kW, €/m²) e dai tetti per intervento. "
            "Calcolarlo sulle tabelle dell'avviso, intervento per intervento"
        )

    # --- affidabilità dei dati ------------------------------------------- #
    if bando.affidabilita_dati == "da_verificare":
        verifiche.append("Scheda bando con dati parziali: verificare sul testo dell'avviso prima di procedere")
        punteggio -= 5
        fattori.append("-5 scheda con dati da verificare")

    # --- esito ------------------------------------------------------------ #
    bloccanti = [e for e in esclusioni if e.bloccante]
    if bloccanti:
        esito = "non_ammissibile"
        punteggio = 0
    elif len(mancanti) >= 3 or len(mancanti_bloccanti) >= 2:
        esito = "dati_insufficienti"
        punteggio = max(10, min(punteggio, 40))
    elif verifiche or avvertenze or mancanti:
        esito = "ammissibile_con_verifiche"
    else:
        esito = "ammissibile"

    punteggio = max(0, min(100, punteggio))
    stima = _stima_agevolazione(bando, imp)

    return EsitoAmmissibilita(
        bando_id=bando.id,
        titolo=bando.titolo,
        esito=esito,
        punteggio_fit=punteggio,
        motivi_esclusione=esclusioni,
        avvertenze=avvertenze,
        verifiche_manuali=verifiche,
        campi_mancanti=sorted(set(mancanti)),
        fattori_punteggio=fattori,
        prossima_scadenza=scad,
        stima_agevolazione_eur=stima,
        sintesi=_sintesi(bando, esito, scad, stima, bloccanti, mancanti),
    )


def _valuta_requisito(
    req: Requisito,
    profilo: ProfiloAzienda,
    esclusioni: list[MotivoEsclusione],
    avvertenze: list[MotivoEsclusione],
    verifiche: list[str],
    mancanti: list[str],
    mancanti_bloccanti: list[str],
) -> None:
    if req.tipo == "dichiarativo" or not req.campo_profilo or not req.operatore:
        verifiche.append(req.descrizione)
        return
    trovato = _get(profilo, req.campo_profilo)
    if trovato is None:
        mancanti.append(req.campo_profilo)
        if req.bloccante:
            mancanti_bloccanti.append(req.campo_profilo)
        return
    try:
        ok = _valuta_operatore(req.operatore, trovato, req.valore)
    except TypeError:
        mancanti.append(req.campo_profilo)
        if req.bloccante:
            mancanti_bloccanti.append(req.campo_profilo)
        return
    if not ok:
        # gli operatori true/false non portano un 'valore': senza questo, 'atteso' arriva
        # all'agente come None e l'esclusione non si spiega da sola
        atteso = req.valore
        if atteso is None and req.operatore in ("true", "false"):
            atteso = req.operatore == "true"
        m = MotivoEsclusione(
            codice=req.codice, descrizione=req.descrizione, campo=req.campo_profilo,
            atteso=atteso, trovato=trovato, bloccante=req.bloccante,
        )
        (esclusioni if req.bloccante else avvertenze).append(m)


def _stima_agevolazione(bando: Bando, importo: Optional[float]) -> Optional[float]:
    """Stima lorda del beneficio: intensità × spesa, tagliata al massimale. Prima delle imposte."""
    if bando.base_calcolo == "massimali_specifici":
        # L'incentivo si calcola sui massimali per unità del bando (€/kW, €/m², tetti per
        # intervento): dal totale di spesa non si ricava una cifra difendibile, meglio nessuna.
        return None
    if importo is None or bando.intensita_max_pct is None:
        return bando.contributo_max_eur
    base = min(importo, bando.spesa_max_eur) if bando.spesa_max_eur else importo
    stima = base * bando.intensita_max_pct / 100
    if bando.contributo_max_eur:
        stima = min(stima, bando.contributo_max_eur)
    return round(stima, 2)


def _sintesi(bando: Bando, esito: str, scad: Scadenza, stima: Optional[float], bloccanti: list, mancanti: list) -> str:
    if esito == "non_ammissibile":
        return f"Escluso: {bloccanti[0].descrizione.lower()}."
    if esito == "dati_insufficienti":
        return f"Servono altri dati per valutare: {', '.join(mancanti[:3])}."
    parti = []
    if stima:
        parti.append(f"agevolazione stimata fino a {stima:,.0f} €")
    if scad.evento == "apertura_invio" and scad.giorni_rimanenti is not None:
        parti.append(f"invio dal {scad.data:%d/%m/%Y} ({scad.giorni_rimanenti} giorni per prepararsi)")
    elif scad.evento == "chiusura" and scad.giorni_rimanenti is not None:
        parti.append(f"chiude il {scad.data:%d/%m/%Y} ({scad.giorni_rimanenti} giorni)")
    elif scad.evento == "sportello_continuo":
        parti.append("sportello sempre aperto")
    return ("Compatibile" if esito == "ammissibile" else "Compatibile con verifiche") + (": " + ", ".join(parti) if parti else "") + "."


def classifica(bandi: list[Bando], profilo: ProfiloAzienda, solo_compatibili: bool = True, oggi: Optional[date] = None) -> list[EsitoAmmissibilita]:
    esiti = [valuta(b, profilo, oggi) for b in bandi]
    if solo_compatibili:
        esiti = [e for e in esiti if e.esito != "non_ammissibile"]
    return sorted(esiti, key=lambda e: (-e.punteggio_fit, e.prossima_scadenza.giorni_rimanenti if e.prossima_scadenza.giorni_rimanenti is not None else 10**6))
