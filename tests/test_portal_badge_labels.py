"""
Badge di stato scadenza DAL PUNTO DI VISTA DEL CLIENTE (speculari all'admin):
cio' che il fornitore "riceve" dal cliente, per il cliente e' "inviato";
le scadenze di pagamento usano "pagato"/"da pagare".
"""
from types import SimpleNamespace

from portal.templatetags.portal_labels import deadline_status_label


def _dl(status, dtype):
    return SimpleNamespace(status=status, deadline_type=dtype)


def test_received_materials_is_inviato():
    # materiale "ricevuto" dal fornitore = INVIATO dal cliente
    assert str(deadline_status_label(_dl('received', 'consegna_materiali'))) == 'Inviato'


def test_received_payment_is_pagato():
    assert str(deadline_status_label(_dl('received', 'pagamento_saldo'))) == 'Pagato'


def test_pending_materials_is_da_inviare():
    assert str(deadline_status_label(_dl('pending', 'consegna_materiali'))) == 'Da inviare'


def test_pending_payment_is_da_pagare():
    assert str(deadline_status_label(_dl('pending', 'pagamento_acconto'))) == 'Da pagare'


def test_waived_is_esonerato():
    assert str(deadline_status_label(_dl('waived', 'pagamento_saldo'))) == 'Esonerato'


def test_overdue_keeps_client_todo_verb():
    # in ritardo: resta il verbo del cliente (da inviare/da pagare), non "ricevuto"
    out = str(deadline_status_label(_dl('overdue', 'consegna_materiali')))
    assert 'inviare' in out.lower()
    assert 'ricevut' not in out.lower()


def test_portal_deadline_templates_compile():
    """I template che usano il filtro/le label compilano (load + filtro ok)."""
    from django.template.loader import get_template
    for t in (
        'portal/contract/detail.html',
        'portal/materials/list.html',
        'portal/events/archived_detail.html',
        'portal/payments/list.html',
    ):
        get_template(t)  # TemplateSyntaxError se load/filtro rotti
