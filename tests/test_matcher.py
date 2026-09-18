from datetime import date

from bandi_mcp import matcher
from bandi_mcp.schema import ProfiloAzienda
from bandi_mcp.store import carica_catalogo, trova_bando

OGGI = date(2026, 9, 18)


def test_catalogo_si_carica_e_ha_fonti():
    bandi = carica_catalogo()
    assert len(bandi) >= 10
    for b in bandi:
        assert b.fonti, f"{b.id} senza fonti"
        assert b.ultimo_controllo <= OGGI


def test_dimensione_impresa():
    assert ProfiloAzienda(addetti_ula=3, fatturato_ultimo_eur=500_000).dimensione == "micro"
    assert ProfiloAzienda(addetti_ula=14, fatturato_ultimo_eur=2_100_000).dimensione == "piccola"
    assert ProfiloAzienda(addetti_ula=120, fatturato_ultimo_eur=30_000_000).dimensione == "media"
    assert ProfiloAzienda(addetti_ula=300).dimensione == "grande"
    assert ProfiloAzienda().dimensione is None


def test_sezione_ateco():
    assert ProfiloAzienda(ateco="25.62").sezione_ateco == "C"
    assert ProfiloAzienda(ateco="62.01").sezione_ateco == "J"
    assert ProfiloAzienda(ateco="55.10").sezione_ateco == "I"
    assert ProfiloAzienda(ateco="C25.62").sezione_ateco == "C"


def test_officina_manifatturiera_passa_investimenti_sostenibili():
    p = ProfiloAzienda(
        ateco="25.62", regione="Sicilia", addetti_ula=14, fatturato_ultimo_eur=2_100_000,
        investimento={"importo_eur": 900_000, "categorie": ["macchinari", "digitale"]},
    )
    e = matcher.valuta(trova_bando("mimit-investimenti-sostenibili-40-2026"), p, OGGI)
    assert e.esito == "ammissibile_con_verifiche"
    assert not e.motivi_esclusione
    assert e.prossima_scadenza.evento == "apertura_invio"
    assert e.prossima_scadenza.giorni_rimanenti == 18
    assert e.stima_agevolazione_eur == 675_000


def test_software_house_esclusa_da_investimenti_sostenibili_per_ateco():
    p = ProfiloAzienda(ateco="62.01", regione="Sicilia", addetti_ula=3, investimento={"importo_eur": 900_000, "categorie": ["digitale"]})
    e = matcher.valuta(trova_bando("mimit-investimenti-sostenibili-40-2026"), p, OGGI)
    assert e.esito == "non_ammissibile"
    assert e.motivi_esclusione[0].codice == "ATECO"


def test_regione_fuori_mezzogiorno_esclusa():
    p = ProfiloAzienda(ateco="25.62", regione="Lombardia", addetti_ula=14, investimento={"importo_eur": 900_000, "categorie": ["macchinari"]})
    e = matcher.valuta(trova_bando("mimit-investimenti-sostenibili-40-2026"), p, OGGI)
    assert any(m.codice == "TERRITORIO" for m in e.motivi_esclusione)


def test_startup_vecchia_esclusa_da_smart_start():
    p = ProfiloAzienda(ateco="62.01", regione="Sicilia", addetti_ula=3, startup_innovativa=True, data_costituzione=date(2015, 1, 1),
                       investimento={"importo_eur": 200_000, "categorie": ["digitale"]})
    e = matcher.valuta(trova_bando("invitalia-smart-start-italia"), p, OGGI)
    assert e.esito == "non_ammissibile"
    assert e.motivi_esclusione[0].codice == "STARTUP_MAX_60_MESI"


def test_requisito_bloccante_non_verificabile_penalizza():
    senza_eta = ProfiloAzienda(ateco="62.01", regione="Sicilia", addetti_ula=3, investimento={"importo_eur": 100_000, "categorie": ["digitale"]})
    con_eta = senza_eta.model_copy(update={"eta_titolare": 29})
    b = trova_bando("invitalia-resto-al-sud-2-0")
    e1, e2 = matcher.valuta(b, senza_eta, OGGI), matcher.valuta(b, con_eta, OGGI)
    assert "eta_titolare" in e1.campi_mancanti
    assert e2.punteggio_fit > e1.punteggio_fit


def test_de_minimis_esaurito_esclude():
    p = ProfiloAzienda(ateco="62.01", regione="Sicilia", addetti_ula=3, connettivita_mbps=100, de_minimis_ricevuti_36_mesi_eur=300_000,
                       investimento={"importo_eur": 10_000, "categorie": ["cloud_cyber"]})
    e = matcher.valuta(trova_bando("mimit-voucher-cloud-cybersecurity-2026"), p, OGGI)
    assert any(m.codice == "DE_MINIMIS_ESAURITO" for m in e.motivi_esclusione)


def test_bando_in_chiusura_valutativo_penalizzato():
    p = ProfiloAzienda(ateco="55.10", regione="Sicilia", addetti_ula=22, investimento={"importo_eur": 1_800_000, "categorie": ["efficienza_energetica"]})
    e = matcher.valuta(trova_bando("mintur-green-tour-2026"), p, OGGI)
    assert e.prossima_scadenza.urgenza == "alta"
    assert any(f.startswith("-15") for f in e.fattori_punteggio)


def test_bando_chiuso_dopo_la_scadenza():
    p = ProfiloAzienda(ateco="55.10", regione="Sicilia", addetti_ula=22, investimento={"importo_eur": 1_800_000, "categorie": ["efficienza_energetica"]})
    e = matcher.valuta(trova_bando("mintur-green-tour-2026"), p, date(2026, 10, 2))
    assert e.esito == "non_ammissibile"
    assert e.motivi_esclusione[0].codice == "STATO_CHIUSO"


def test_zes_unica_finestra_2026_chiusa():
    """La comunicazione preventiva chiudeva il 30/05/2026: oggi il credito 2026 non è più accessibile."""
    p = ProfiloAzienda(
        ateco="25.62", regione="Sicilia", addetti_ula=14, fatturato_ultimo_eur=2_100_000,
        investimento={"importo_eur": 900_000, "categorie": ["macchinari", "impianti"]},
    )
    e = matcher.valuta(trova_bando("zes-unica-credito-imposta-2026"), p, OGGI)
    assert e.esito == "non_ammissibile"
    assert e.motivi_esclusione[0].codice == "STATO_CHIUSO"
