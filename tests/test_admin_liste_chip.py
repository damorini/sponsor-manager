"""Le liste admin: chip visibili, commenti non stampati, niente sovrapposizioni.

Due problemi veri, visti in produzione dal browser di Daniele:

1. Un commento `{# ... #}` scritto su DUE righe viene STAMPATO nella pagina
   (il tag vale su una riga sola). Compariva sopra la lista contratti.
2. Il bottone "Aggiungi contratto" copriva i chip "Cose da fare" sugli
   schermi stretti: Django da' a .object-tools float:right con
   margin-top:-48px, e i chip stavano PRIMA nel DOM.
"""
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

RADICE = Path(settings.BASE_DIR)

TEMPLATE_ADMIN = [
    "contracts/templates/admin/contracts/contract/change_list.html",
    "contracts/templates/admin/contracts/deadline/change_list.html",
]


@pytest.fixture
def admin_client_locale(db, client):
    from django.contrib.auth import get_user_model
    utente = get_user_model().objects.create_superuser(
        username='boss_chip', email='boss.chip@test.it',
        password='AdminPass123!')
    client.force_login(utente)
    return client


def _tutti_i_template():
    cartelle = ["templates", "contracts", "core", "shared", "sponsors",
                "catalog", "venues", "events", "users", "portal"]
    for cartella in cartelle:
        base = RADICE / cartella
        if not base.exists():
            continue
        for percorso in base.rglob("*.html"):
            if "venv" in percorso.parts:
                continue
            yield percorso


def test_nessun_commento_django_aperto_su_piu_righe():
    """`{#` deve chiudersi sulla stessa riga, altrimenti finisce a schermo."""
    colpevoli = []
    for percorso in _tutti_i_template():
        for numero, riga in enumerate(
                percorso.read_text(encoding="utf-8").splitlines(), start=1):
            if "{#" in riga and "#}" not in riga:
                colpevoli.append(f"{percorso.relative_to(RADICE)}:{numero}")
    assert not colpevoli, (
        "questi commenti vengono STAMPATI nella pagina: usa "
        "{% comment %}...{% endcomment %}\n  " + "\n  ".join(colpevoli))


@pytest.mark.parametrize("percorso", TEMPLATE_ADMIN)
def test_i_chip_stanno_dopo_il_bottone_aggiungi(percorso):
    """Nel DOM i chip devono venire dopo object-tools, o il bottone li copre."""
    testo = (RADICE / percorso).read_text(encoding="utf-8")
    assert "{% block object-tools %}" in testo, (
        "i chip vanno dentro il blocco object-tools")
    posizione_super = testo.index("{{ block.super }}")
    posizione_chip = testo.index('class="vt-chips"')
    assert posizione_super < posizione_chip, (
        "block.super (che rende il bottone Aggiungi) deve venire prima "
        "dei chip")


def test_i_chip_hanno_il_clear():
    """Senza clear:both il bottone floatato ci finisce sopra."""
    css = (RADICE / "core/templates/admin/base_site.html").read_text(
        encoding="utf-8")
    blocco = re.search(r"\.vt-chips\s*\{[^}]*\}", css)
    assert blocco, "regola .vt-chips non trovata"
    assert "clear" in blocco.group(0), (
        ".vt-chips deve avere clear:both per stare sotto .object-tools")


@pytest.mark.django_db
def test_la_lista_contratti_si_apre_e_non_stampa_il_commento(
        admin_client_locale):
    risposta = admin_client_locale.get(
        reverse("admin:contracts_contract_changelist"))
    assert risposta.status_code == 200
    testo = risposta.content.decode()
    assert "Cose da fare" in testo
    assert "Da inviare" in testo
    # Il sintomo esatto: il TESTO del commento che finiva a schermo.
    # Non basta cercare "Scorciatoie": quella parola sta anche in un
    # commento CSS dentro <style>, innocuo, e l'asserzione passerebbe o
    # fallirebbe per motivi che non c'entrano.
    # "SEMPRE VISIBILI" compare SOLO dentro quel commento: e' il
    # marcatore giusto. Attenzione a scegliere stringhe generiche
    # ("Scorciatoie" sta anche in un commento CSS, "pannello filtri di
    # destra" in un commento JavaScript): passerebbero o fallirebbero
    # per motivi che col difetto non c'entrano.
    assert "SEMPRE VISIBILI" not in testo, (
        "il commento del template sta finendo nella pagina")
    assert "{#" not in testo


@pytest.mark.django_db
def test_la_lista_scadenze_si_apre_e_non_stampa_il_commento(
        admin_client_locale):
    risposta = admin_client_locale.get(
        reverse("admin:contracts_deadline_changelist"))
    assert risposta.status_code == 200
    testo = risposta.content.decode()
    assert "Vedi subito" in testo
    assert "un click per gli stati" not in testo, (
        "il commento del template sta finendo nella pagina")
    assert "{#" not in testo


@pytest.mark.django_db
def test_il_bottone_aggiungi_c_e_ancora(admin_client_locale):
    """Spostando i chip dentro object-tools non deve sparire il bottone."""
    risposta = admin_client_locale.get(
        reverse("admin:contracts_contract_changelist"))
    testo = risposta.content.decode()
    assert "addlink" in testo or "Aggiungi" in testo
    assert 'class="object-tools"' in testo
