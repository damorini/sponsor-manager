"""
Il menu admin (sidebar) e' raggruppato in sezioni logiche invece che per app.
"""
import pytest


def _superuser():
    from django.contrib.auth import get_user_model
    U = get_user_model()
    return U.objects.create_superuser('gadmin', 'gadmin@test.it', 'x')


@pytest.mark.django_db
def test_grouped_app_list(rf):
    from django.contrib import admin
    req = rf.get('/admin/contracts/contract/')
    req.user = _superuser()

    app_list = admin.site.get_app_list(req)
    names = [a['name'] for a in app_list]

    assert any('Contratti' in n for n in names)
    assert any('Sponsor' in n for n in names)
    assert any('Catalogo' in n for n in names)
    assert any('Configurazione' in n for n in names)

    contratti = next(a for a in app_list if 'Contratti' in a['name'])
    objs = [m['object_name'] for m in contratti['models']]
    assert {'Contract', 'Deadline', 'Payment'} <= set(objs)

    cfg = next(a for a in app_list if 'Configurazione' in a['name'])
    assert 'User' in [m['object_name'] for m in cfg['models']]


@pytest.mark.django_db
def test_admin_page_renders_grouped_sidebar(client):
    client.force_login(_superuser())
    resp = client.get('/admin/contracts/contract/')
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'Contratti' in html and 'Catalogo' in html
