"""Il menu dell'admin non deve perdere pezzi.

Il menu NON e' piu' costruito da core/admin_grouping.py: la sidebar e
l'indice passano da core/templates/admin/app_list.html, che elenca i
modelli UNO PER UNO in sei gruppi scritti a mano. Un modello nuovo che
nessuno aggiunge a quel template non compare in nessun punto del menu, e
l'unico modo di raggiungerlo e' conoscerne l'URL.

E' successo con la Rubrica: Aree di interesse, Campagne e Email escluse
erano registrate in admin e raggiungibili per URL, ma invisibili nel
menu, e il test sul raggruppamento dinamico passava perche' misurava
codice che la sidebar non usa piu'.
"""
import pytest
from django.contrib import admin
from django.urls import reverse


@pytest.fixture
def admin_client_vero(client, db):
    from users.models import User
    u = User.objects.create_superuser(
        username='menu', email='menu@valet.it', password='x')
    client.force_login(u)
    return client


def _menu(client):
    """L'HTML di una pagina admin qualsiasi: la sidebar c'e' su tutte."""
    r = client.get(reverse('admin:sponsors_sponsor_changelist'))
    assert r.status_code == 200
    return r.content.decode()


@pytest.mark.django_db
class TestVociDellaRubrica:

    @pytest.mark.parametrize('url_nome', [
        'admin:sponsors_interestarea_changelist',
        'admin:sponsors_interestcampaign_changelist',
        'admin:sponsors_suppressedemail_changelist',
    ])
    def test_la_voce_e_nel_menu(self, admin_client_vero, url_nome):
        assert reverse(url_nome) in _menu(admin_client_vero)


@pytest.mark.django_db
class TestNessunModelloResiFuori:
    """La rete di sicurezza: vale anche per i modelli che verranno."""

    def test_ogni_modello_registrato_compare_nel_menu(self, admin_client_vero):
        html = _menu(admin_client_vero)
        mancanti = []
        for modello in admin.site._registry:
            meta = modello._meta
            url = reverse(
                f'admin:{meta.app_label}_{meta.model_name}_changelist')
            if url not in html:
                mancanti.append(f'{modello.__name__} ({url})')
        assert not mancanti, (
            'modelli registrati in admin ma assenti dal menu: '
            + ', '.join(sorted(mancanti))
        )


@pytest.mark.django_db
class TestNienteCommentiStampati:
    """In un template Django ogni {# deve chiudersi con #} sulla STESSA riga:
    un commento su piu' righe viene STAMPATO nella pagina.

    Il marcatore e' una frase che compare SOLO dentro quel commento
    (verificato con grep su tutto il repo): "rete di sicurezza" no, perche'
    sta anche in un commento JavaScript del portale, e il test passerebbe o
    fallirebbe per un motivo che col difetto non c'entra.
    """

    def test_il_commento_della_sezione_altro_non_finisce_nella_pagina(
            self, admin_client_vero):
        assert 'raggiungibile solo conoscendone' not in _menu(
            admin_client_vero)
