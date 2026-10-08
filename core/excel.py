"""Lettura dei fogli Excel per gli import."""
from openpyxl.utils.escape import unescape


def _pulisci(valore):
    # Excel salva l'a capo dentro una cella come "_x000D_" (e altri caratteri
    # di controllo come "_xHHHH_"): openpyxl non li riconverte, e finivano
    # cosi' nelle descrizioni dei servizi.
    if not isinstance(valore, str):
        return valore
    return unescape(valore).replace("\r\n", "\n").replace("\r", "\n")


def righe_excel(ws):
    """Tutte le righe del foglio come tuple di valori, testi gia' ripuliti."""
    return [tuple(_pulisci(v) for v in riga) for riga in ws.iter_rows(values_only=True)]
