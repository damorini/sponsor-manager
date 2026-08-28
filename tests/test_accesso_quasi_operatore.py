"""Pagina 'Ci siamo quasi': se chi la vede e' un OPERATORE loggato, deve
capire il perche' e avere il pulsante per uscire (prima 'Accedi al portale'
sembrava un loop senza uscita)."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


@pytest.mark.django_db
def test_operatore_vede_avviso_e_logout(client):
    u = get_user_model().objects.create_user(
        username='op_quasi', email='op_quasi@valet.it', password='x',
        is_staff=True)
    u.role = 'operator'
    u.save()
    client.force_login(u)
    resp = client.get(reverse('portal:dashboard'))
    assert resp.status_code == 403  # respinto, pagina di cortesia
    html = resp.content.decode()
    assert 'OPERATORE del backoffice' in html
    assert reverse('portal:logout') in html


@pytest.mark.django_db
def test_anonimo_non_vede_avviso_operatore(client):
    resp = client.get(reverse('portal:dashboard'), follow=True)
    assert 'OPERATORE del backoffice' not in resp.content.decode()
