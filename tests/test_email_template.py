"""
EmailTemplate: i campi Oggetto/Corpo sono multilingua (JSONField) e devono
persistere al salvataggio dall'admin (prima erano Char/Text e il dict finiva
serializzato come repr Python -> campi "vuoti" al reload).
"""
import pytest

from shared.models import EmailTemplate
from shared.admin import EmailTemplateForm
from contracts.services.email_sender import _pick_lang


@pytest.mark.django_db
def test_salvataggio_oggetto_e_corpo_bilingue_persiste():
    tpl = EmailTemplate.objects.create(
        code='test_persist', name='Prova', communication_type='manual',
        subject_template={}, body_template={},
    )
    data = {
        'code': tpl.code, 'name': tpl.name, 'description': '',
        'communication_type': 'manual', 'language': 'it',
        'is_active': 'on',
        'subject_template_0': 'Oggetto IT', 'subject_template_1': 'Subject EN',
        'body_template_0': '<p>Corpo IT</p>', 'body_template_1': '<p>Body EN</p>',
    }
    form = EmailTemplateForm(data, instance=tpl)
    assert form.is_valid(), form.errors
    obj = form.save()
    obj.refresh_from_db()

    assert obj.subject_template == {'it': 'Oggetto IT', 'en': 'Subject EN'}
    assert obj.body_template == {'it': '<p>Corpo IT</p>', 'en': '<p>Body EN</p>'}


@pytest.mark.django_db
def test_pick_lang_legge_dict_e_stringhe_legacy():
    # dict (nuovo formato JSONField)
    assert _pick_lang({'it': 'Ciao', 'en': 'Hi'}, 'en') == 'Hi'
    assert _pick_lang({'it': 'Ciao', 'en': 'Hi'}, 'it') == 'Ciao'
    # fallback alla lingua presente
    assert _pick_lang({'it': 'Ciao'}, 'en') == 'Ciao'
    # vecchia repr Python (compat)
    assert _pick_lang("{'it': 'Ciao', 'en': 'Hi'}", 'en') == 'Hi'
    # testo semplice
    assert _pick_lang('testo', 'it') == 'testo'
