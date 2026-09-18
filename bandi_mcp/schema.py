"""
Modello dati di Bandi MCP.

Tre entità:
- ProfiloAzienda: chi chiede (costruito dall'agente, non da un form)
- Bando: una misura di finanza agevolata normalizzata in modo che una macchina
  possa ragionarci sopra (requisiti strutturati, date separate, categorie di spesa)
- EsitoAmmissibilita: cosa risponde il motore, con motivi strutturati
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, computed_field

Dimensione = Literal["micro", "piccola", "media", "grande"]

CategoriaSpesa = Literal[
    "macchinari",
    "impianti",
    "digitale",
    "cloud_cyber",
    "formazione",
    "ricerca_sviluppo",
    "efficienza_energetica",
    "rinnovabili",
    "proprieta_intellettuale",
    "assunzioni",
    "internazionalizzazione",
    "riqualificazione_turistica",
    "avvio_impresa",
    "welfare_conciliazione",
    "capitale_circolante",
    "consulenza",
    "produzione_culturale",
    "personale_ricerca",
    "design",
    "sicurezza_lavoro",
]

FormaGiuridica = Literal[
    "ditta_individuale",
    "libero_professionista",
    "snc",
    "sas",
    "srl",
    "srls",
    "spa",
    "cooperativa",
    "impresa_sociale",
    "ets",
    "da_costituire",
]


# --------------------------------------------------------------------------- #
# Profilo azienda
# --------------------------------------------------------------------------- #
class InvestimentoPrevisto(BaseModel):
    """Cosa l'azienda vuole fare con i soldi."""

    importo_eur: Optional[float] = Field(None, description="Spesa complessiva prevista, IVA esclusa")
    categorie: list[CategoriaSpesa] = Field(default_factory=list)
    descrizione: Optional[str] = None
    avvio_previsto: Optional[date] = Field(
        None, description="Quando l'azienda vorrebbe iniziare a spendere. Serve per il vincolo 'spese dopo la domanda'."
    )


class ProfiloAzienda(BaseModel):
    """
    Profilo minimo per ragionare sui bandi. Tutti i campi sono opzionali:
    il motore segnala cosa manca invece di rifiutare.
    L'agente lo costruisce da P.IVA, visura, bilancio, sito e conversazione.
    """

    ragione_sociale: Optional[str] = None
    partita_iva: Optional[str] = None
    ateco: Optional[str] = Field(None, description="Codice ATECO 2025 principale, es. '62.01' o 'C25.62'")
    forma_giuridica: Optional[FormaGiuridica] = None

    regione: Optional[str] = Field("Sicilia", description="Regione della sede operativa dell'investimento")
    provincia: Optional[str] = None
    comune: Optional[str] = None
    sede_operativa_in_sicilia: Optional[bool] = True
    unita_produttiva_fuori_sicilia: Optional[bool] = Field(
        None, description="True se l'impresa ha unità produttive fuori dalla Sicilia (rileva per South Working)"
    )

    addetti_ula: Optional[float] = Field(None, description="Unità lavorative annue dell'ultimo esercizio")
    fatturato_ultimo_eur: Optional[float] = None
    fatturato_medio_2_esercizi_eur: Optional[float] = None
    totale_bilancio_eur: Optional[float] = None
    mol_ultimi_2_esercizi_eur: Optional[list[float]] = Field(
        None, description="Margine operativo lordo degli ultimi due bilanci, dal più recente"
    )
    data_costituzione: Optional[date] = None

    startup_innovativa: Optional[bool] = Field(None, description="Iscritta alla sezione speciale del Registro Imprese")
    compagine_giovanile_under36: Optional[bool] = Field(
        None, description="Titolare o maggioranza dei soci con meno di 36 anni"
    )
    eta_titolare: Optional[int] = None
    compagine_femminile: Optional[bool] = None
    filiera_culturale_creativa: Optional[bool] = None
    brevetto_registrato: Optional[bool] = None
    certificazione_parita_genere: Optional[bool] = None

    de_minimis_ricevuti_36_mesi_eur: Optional[float] = Field(
        None, description="Aiuti de minimis concessi nel triennio mobile (verificare su RNA)"
    )
    durc_regolare: Optional[bool] = None
    connettivita_mbps: Optional[int] = Field(None, description="Banda in download del contratto attivo")
    dipendenti_totali: Optional[int] = None
    assunzioni_indeterminato_dopo_2026_01_09: Optional[int] = Field(
        None, description="Nuove assunzioni a tempo indeterminato dopo il 9/1/2026 (South Working)"
    )

    investimento: InvestimentoPrevisto = Field(default_factory=InvestimentoPrevisto)

    @computed_field  # type: ignore[misc]
    @property
    def dimensione(self) -> Optional[Dimensione]:
        """Classificazione UE (Racc. 2003/361). Serve almeno il dato addetti."""
        if self.addetti_ula is None:
            return None
        fatt = self.fatturato_ultimo_eur
        bil = self.totale_bilancio_eur

        def sotto(fatt_max: float, bil_max: float) -> bool:
            if fatt is None and bil is None:
                return True  # ottimista: verrà segnalato come dato da confermare
            return (fatt is not None and fatt <= fatt_max) or (bil is not None and bil <= bil_max)

        if self.addetti_ula < 10 and sotto(2_000_000, 2_000_000):
            return "micro"
        if self.addetti_ula < 50 and sotto(10_000_000, 10_000_000):
            return "piccola"
        if self.addetti_ula < 250 and sotto(50_000_000, 43_000_000):
            return "media"
        return "grande"

    @computed_field  # type: ignore[misc]
    @property
    def eta_impresa_mesi(self) -> Optional[int]:
        if self.data_costituzione is None:
            return None
        oggi = date.today()
        return (oggi.year - self.data_costituzione.year) * 12 + (oggi.month - self.data_costituzione.month)

    @computed_field  # type: ignore[misc]
    @property
    def impresa_nuova_o_da_costituire(self) -> Optional[bool]:
        """
        Vero se l'impresa è ancora da costituire o è stata avviata nel mese corrente o in quello
        precedente. È il perimetro delle misure di autoimpiego (Resto al Sud 2.0). None quando non
        si può dire: chi chiama lo vedrà in campi_mancanti, non come un no.
        """
        if self.forma_giuridica == "da_costituire":
            return True
        mesi = self.eta_impresa_mesi
        if mesi is None:
            return None
        return mesi <= 1

    @computed_field  # type: ignore[misc]
    @property
    def sezione_ateco(self) -> Optional[str]:
        """Lettera di sezione ATECO (A..U) ricavata dal codice."""
        if not self.ateco:
            return None
        code = self.ateco.strip().upper()
        if code[0].isalpha():
            return code[0]
        # mappa divisione numerica -> sezione
        try:
            div = int(code.split(".")[0])
        except ValueError:
            return None
        return _divisione_a_sezione(div)


def _divisione_a_sezione(div: int) -> Optional[str]:
    tabella = [
        (1, 3, "A"), (5, 9, "B"), (10, 33, "C"), (35, 35, "D"), (36, 39, "E"),
        (41, 43, "F"), (45, 47, "G"), (49, 53, "H"), (55, 56, "I"), (58, 63, "J"),
        (64, 66, "K"), (68, 68, "L"), (69, 75, "M"), (77, 82, "N"), (84, 84, "O"),
        (85, 85, "P"), (86, 88, "Q"), (90, 93, "R"), (94, 96, "S"), (97, 98, "T"), (99, 99, "U"),
    ]
    for lo, hi, sez in tabella:
        if lo <= div <= hi:
            return sez
    return None


# --------------------------------------------------------------------------- #
# Bando
# --------------------------------------------------------------------------- #
class Requisito(BaseModel):
    """
    Un requisito di accesso, leggibile da una macchina.
    - automatico: valutato sul profilo (campo_profilo + operatore + valore)
    - dichiarativo: non verificabile da noi, va confermato dall'utente/consulente
    """

    codice: str
    descrizione: str
    tipo: Literal["automatico", "dichiarativo"] = "automatico"
    campo_profilo: Optional[str] = Field(None, description="Path nel ProfiloAzienda, es. 'investimento.importo_eur'")
    operatore: Optional[Literal["==", "!=", ">=", "<=", "<", ">", "in", "not_in", "between", "true", "false", "prefix_in"]] = None
    valore: Any = None
    bloccante: bool = True


class DateBando(BaseModel):
    apertura_compilazione: Optional[date] = None
    apertura_invio: Optional[date] = None
    chiusura: Optional[date] = None
    orario_chiusura: Optional[str] = None
    ammissibilita_spese_da: Optional[str] = Field(
        None,
        description="Da quando le spese sono ammissibili: 'presentazione_domanda', 'concessione', "
        "'richiesta_preliminare', 'pec_domanda_banca', o una data ISO",
    )
    termine_realizzazione: Optional[str] = None


class Fonte(BaseModel):
    url: str
    tipo: Literal["ufficiale", "secondaria"]
    titolo: Optional[str] = None


class Bando(BaseModel):
    id: str
    titolo: str
    ente: str
    gestore: Optional[str] = None
    livello: Literal["ue", "nazionale", "regionale", "camerale"]
    territori: list[str] = Field(description="Regioni ammesse; ['IT'] = tutta Italia; ['UE'] = Unione Europea")
    stato: Literal["aperto", "sportello_continuo", "in_apertura", "in_chiusura", "chiuso", "sospeso"]
    procedura: Literal["cronologico", "cronologico_giornaliero", "valutativa", "graduatoria", "automatica"]

    agevolazioni: list[
        Literal[
            "fondo_perduto",
            "finanziamento_agevolato",
            "tasso_zero",
            "credito_imposta",
            "voucher",
            "garanzia",
            "contributo_interessi",
            "maggiorazione_ammortamento",
        ]
    ]
    intensita_max_pct: Optional[float] = None
    intensita_fondo_perduto_pct: Optional[float] = None
    contributo_max_eur: Optional[float] = None
    spesa_min_eur: Optional[float] = None
    spesa_max_eur: Optional[float] = None
    dotazione_eur: Optional[float] = None
    base_calcolo: Literal[
        "spesa_ammissibile", "massimali_specifici", "maggiorazione_ammortamento", "garanzia"
    ] = Field(
        "spesa_ammissibile",
        description="Come si determina il beneficio, e quindi se il motore può stimarlo dal totale di spesa. "
        "'spesa_ammissibile': intensità × spesa, l'unico caso in cui la stima ha senso. "
        "'massimali_specifici': dipende da massimali per unità (€/kW, €/m²) e tetti per intervento. "
        "'maggiorazione_ammortamento': è una deduzione fiscale, il beneficio dipende dall'aliquota e dal "
        "reddito imponibile dell'impresa. 'garanzia': non è una somma, è accesso al credito.",
    )

    dimensioni_ammesse: list[Dimensione] = Field(default_factory=lambda: ["micro", "piccola", "media"])
    beneficiari: list[
        Literal["impresa", "startup_innovativa", "libero_professionista", "ets", "persona_fisica", "impresa_sociale", "impresa_da_costituire"]
    ] = Field(default_factory=lambda: ["impresa"])
    ateco_ammessi: Optional[list[str]] = Field(None, description="Prefissi ATECO ammessi (sezione o divisione). None = tutti")
    ateco_esclusi: list[str] = Field(default_factory=list)
    categorie_spesa: list[CategoriaSpesa] = Field(default_factory=list)

    calendario: DateBando = Field(default_factory=DateBando)
    requisiti: list[Requisito] = Field(default_factory=list)
    regime_aiuti: Optional[Literal["de_minimis", "gber", "esenzione_art17", "misto", "fuori_regime"]] = None
    riserve: list[str] = Field(default_factory=list, description="Quote riservate, es. '25% micro e piccole imprese'")
    documenti: list[str] = Field(default_factory=list)
    piattaforma: Optional[str] = None

    fonti: list[Fonte] = Field(default_factory=list)
    ultimo_controllo: date
    affidabilita_dati: Literal["ufficiale", "secondaria", "da_verificare"] = "secondaria"
    note: list[str] = Field(default_factory=list)
    tag: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Esito
# --------------------------------------------------------------------------- #
class MotivoEsclusione(BaseModel):
    codice: str
    descrizione: str
    campo: Optional[str] = None
    atteso: Any = None
    trovato: Any = None
    bloccante: bool = True


class Scadenza(BaseModel):
    evento: Literal["apertura_compilazione", "apertura_invio", "chiusura", "sportello_continuo", "in_apertura"]
    data: Optional[date] = None
    giorni_rimanenti: Optional[int] = None
    urgenza: Literal["alta", "media", "bassa", "nessuna"] = "nessuna"


class EsitoAmmissibilita(BaseModel):
    bando_id: str
    titolo: str
    esito: Literal["ammissibile", "ammissibile_con_verifiche", "non_ammissibile", "dati_insufficienti"]
    punteggio_fit: int = Field(ge=0, le=100)
    motivi_esclusione: list[MotivoEsclusione] = Field(default_factory=list)
    avvertenze: list[MotivoEsclusione] = Field(default_factory=list, description="Requisiti non bloccanti non soddisfatti")
    verifiche_manuali: list[str] = Field(default_factory=list, description="Requisiti dichiarativi da confermare")
    campi_mancanti: list[str] = Field(default_factory=list)
    fattori_punteggio: list[str] = Field(default_factory=list)
    prossima_scadenza: Scadenza
    stima_agevolazione_eur: Optional[float] = None
    sintesi: str
