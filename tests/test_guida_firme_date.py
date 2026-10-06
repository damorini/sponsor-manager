"""Guida alle firme: conta anche i blocchi firma con la data gia' stampata
(contratto e Domanda), non solo quelli con «Data ______»."""
from contracts.services.guida_firme import firme_per_pagina


class _Pagina:
    def __init__(self, testo):
        self.testo = testo

    def extract_text(self):
        return self.testo


class _Lettore:
    def __init__(self, *testi):
        self.pages = [_Pagina(t) for t in testi]


def test_conta_le_firme_con_e_senza_data_stampata():
    contratto = ("14.1 Il contratto e' regolato dal diritto italiano.\n"
                 "Bologna,  05/10/2026\nSponsor\n________\n"
                 "Le parti dichiarano...\nBologna,  05/10/2026\nSponsor\n________")
    domanda = ("Le finiture dovranno essere di colore bianco.\n"
               "Bologna, 05/10/2026\nPROMOITALIA GROUP SPA\nValerio Matano")
    allegato2 = "Data ____________________\nTimbro e firma\nData ____________________"
    # una data dentro il testo non e' una firma
    testo = "Il congresso si terra' a Bologna, 25/02/2027 - 27/02/2027 presso il Palazzo."
    r = _Lettore(contratto, domanda, allegato2, testo)
    assert firme_per_pagina(r, 0, 3) == [(0, 2), (1, 1), (2, 2)]
