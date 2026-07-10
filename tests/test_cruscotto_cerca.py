"""
Ricerca sponsor globale dal cruscotto (hero).

- GET /admin/cruscotto/cerca/?q=... cerca per ragione sociale, P.IVA e
  nome/email dei contatti; esclude gli sponsor nel cestino (soft-delete).
- La home del cruscotto espone il form di ricerca che punta alla view.
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from sponsors.models import Contact, Sponsor

User = get_user_model()


@pytest.fixture
def staff_client(client, db):
    op = User.objects.create_user(
        username='op_cerca', email='op.cerca@test.it', password='x',
        is_staff=True, is_superuser=True, is_active=True)
    client.force_login(op)
    # scelta evento gia' fatta ('tutti'): il cruscotto non redirige al picker
    from core.event_scope import SESSION_EVENT_CHOSEN
    s = client.session
    s[SESSION_EVENT_CHOSEN] = True
    s.save()
    return client


def _sponsor(name, vat):
    return Sponsor.objects.create(
        legal_name=name, vat_number=vat, address_country='IT')


@pytest.mark.django_db
def test_cerca_per_ragione_sociale(staff_client):
    sp = _sponsor('ACME Congressi S.r.l.', '11111111111')
    _sponsor('Altra Ditta S.p.A.', '22222222222')
    resp = staff_client.get(reverse('core:cruscotto_cerca'), {'q': 'acme'})
    assert resp.status_code == 200
    assert [r['id'] for r in resp.context['risultati']] == [sp.id]


@pytest.mark.django_db
def test_cerca_per_partita_iva(staff_client):
    sp = _sponsor('ACME Congressi S.r.l.', '11111111111')
    _sponsor('Altra Ditta S.p.A.', '22222222222')
    resp = staff_client.get(reverse('core:cruscotto_cerca'), {'q': '11111111111'})
    assert [r['id'] for r in resp.context['risultati']] == [sp.id]


@pytest.mark.django_db
def test_cerca_per_contatto(staff_client):
    sp = _sponsor('ACME Congressi S.r.l.', '11111111111')
    Contact.objects.create(
        sponsor=sp, full_name='Mario Rossi', email='mario.rossi@acme.it')
    resp = staff_client.get(reverse('core:cruscotto_cerca'), {'q': 'mario.rossi'})
    assert [r['id'] for r in resp.context['risultati']] == [sp.id]


@pytest.mark.django_db
def test_cerca_esclude_cestinati(staff_client):
    sp = _sponsor('ACME Congressi S.r.l.', '11111111111')
    sp.delete()  # soft-delete: nel cestino, non deve comparire
    resp = staff_client.get(reverse('core:cruscotto_cerca'), {'q': 'acme'})
    assert resp.context['risultati'] == []


@pytest.mark.django_db
def test_cerca_q_vuota_non_mostra_risultati(staff_client):
    _sponsor('ACME Congressi S.r.l.', '11111111111')
    resp = staff_client.get(reverse('core:cruscotto_cerca'))
    assert resp.status_code == 200
    assert resp.context['risultati'] == []


@pytest.mark.django_db
def test_cerca_richiede_staff(client):
    resp = client.get(reverse('core:cruscotto_cerca'), {'q': 'acme'})
    assert resp.status_code == 302  # redirect al login


@pytest.mark.django_db
def test_risultato_ha_link_scheda_admin(staff_client):
    sp = _sponsor('ACME Congressi S.r.l.', '11111111111')
    resp = staff_client.get(reverse('core:cruscotto_cerca'), {'q': 'acme'})
    atteso = reverse('admin:sponsors_sponsor_change', args=[sp.id])
    assert atteso in resp.content.decode()


@pytest.mark.django_db
def test_home_cruscotto_ha_form_di_ricerca(staff_client):
    resp = staff_client.get(reverse('core:cruscotto_home'))
    assert reverse('core:cruscotto_cerca') in resp.content.decode()
