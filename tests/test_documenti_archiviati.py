"""Pagina del contratto aperta, poi «Anteprima preventivo» in un'altra scheda
(il PDF vecchio viene archiviato): salvando la pagina non deve chiedere di
caricare un file ne' creare documenti."""
from datetime import date

import pytest


def _formset(contratto, doc, cancella=False):
    from django.contrib.contenttypes.forms import generic_inlineformset_factory
    from shared.admin import DocumentUploadForm, _DocumentiFormSet
    from shared.models import Document

    FS = generic_inlineformset_factory(
        Document, form=DocumentUploadForm, formset=_DocumentiFormSet,
        fields=('document_type', 'title', 'is_visible_to_sponsor'), extra=0, can_delete=True)
    prefix = FS.get_default_prefix()
    data = {
        f'{prefix}-TOTAL_FORMS': '1', f'{prefix}-INITIAL_FORMS': '1',
        f'{prefix}-MIN_NUM_FORMS': '0', f'{prefix}-MAX_NUM_FORMS': '1000',
        f'{prefix}-0-id': str(doc.pk),
        f'{prefix}-0-document_type': doc.document_type,
        f'{prefix}-0-title': doc.title,
        f'{prefix}-0-is_visible_to_sponsor': 'on',
    }
    if cancella:
        data[f'{prefix}-0-DELETE'] = 'on'
    return FS(data=data, instance=contratto)


def _contratto_con_pdf_archiviato(sponsor):
    from django.contrib.contenttypes.models import ContentType
    from contracts.models import Contract, ContractKind, ContractStatus
    from events.models import Event
    from shared.models import Document

    ev = Event.objects.create(name={'it': 'Ev'}, code='DOCA',
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))
    c = Contract.objects.create(sponsor=sponsor, event=ev, language='it',
                                contract_kind=ContractKind.MAIN, status=ContractStatus.DRAFT)
    doc = Document.objects.create(
        content_type=ContentType.objects.get_for_model(Contract), object_id=c.pk,
        document_type='quote', title='preventivo.pdf', file_name='preventivo.pdf',
        storage_url='http://x/preventivo.pdf')
    doc.delete()  # archiviato dall'anteprima
    return c, doc


@pytest.mark.django_db
@pytest.mark.parametrize('cancella', [False, True])
def test_pdf_archiviato_non_blocca_il_salvataggio(sponsor, cancella):
    from shared.models import Document

    c, doc = _contratto_con_pdf_archiviato(sponsor)
    fs = _formset(c, doc, cancella=cancella)
    assert fs.is_valid(), fs.errors
    for obj in fs.save(commit=False):
        obj.save()
    for obj in fs.deleted_objects:
        obj.delete()
    assert Document.all_objects.count() == 1
    assert not Document.objects.exists()
