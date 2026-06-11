"""
Il form Evento usa il selettore a due finestre (FilteredSelectMultiple) per
i servizi del catalogo, invece dei checkbox.
"""
import pytest


@pytest.mark.django_db
def test_event_add_form_uses_dual_list(client):
    from django.contrib.auth import get_user_model
    U = get_user_model()
    u = U.objects.create_superuser('ev_admin', 'ev@test.it', 'x')
    client.force_login(u)

    resp = client.get('/admin/events/event/add/')
    assert resp.status_code == 200
    html = resp.content.decode()
    # Il widget a due finestre carica SelectFilter2.js e marca il <select> come selectfilter
    assert 'SelectFilter2.js' in html
    assert 'selectfilter' in html
