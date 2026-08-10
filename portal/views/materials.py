"""
View per gestione materiali sponsor.

Concetti:
- Deadline = richiesta operativa (es. "Logo HD entro 30 giorni dall'evento")
- Document = file caricato dallo sponsor che soddisfa la deadline

Lo sponsor vede:
- Lista materiali per contratto (= lista Deadline filtrate)
- Per ogni deadline: stato + materiali già caricati + form upload
- Quando carica un file, la deadline passa a RECEIVED

Validazioni upload:
- Tipo MIME consentito (configurabile per deadline)
- Dimensione massima (default 20 MB, configurabile)
- Estensione valida
"""
import logging
import mimetypes
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from portal.views.dashboard import sponsor_required

logger = logging.getLogger(__name__)


# ============================================================================
# Configurazione upload
# ============================================================================

DEFAULT_MAX_UPLOAD_SIZE_MB = 20

DEFAULT_ALLOWED_MIME_TYPES = [
    'application/pdf',
    'image/jpeg', 'image/png', 'image/webp', 'image/svg+xml',
    'application/zip',
    'application/illustrator', 'application/postscript',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]

# Whitelist di ESTENSIONI: il content-type dichiarato dal browser e'
# falsificabile, l'estensione del nome file no (decide anche il nome con cui
# il file viene salvato). Un .html "spacciato" per application/pdf viene
# rifiutato qui.
ALLOWED_UPLOAD_EXTENSIONS = {
    '.pdf', '.jpg', '.jpeg', '.png', '.webp', '.svg',
    '.zip', '.ai', '.eps',
    '.xls', '.xlsx', '.doc', '.docx',
}


# ============================================================================
# Helper: lista materiali per un contratto
# ============================================================================

def _payment_info(d):
    """Per scadenze di pagamento: (is_payment, importo, etichetta).
    L'importo non e' sulla scadenza ma sul contratto (acconto/saldo/totale)."""
    dtype = (d.deadline_type or '')
    if not (dtype.startswith('pagamento') or dtype == 'scadenza_opzione'):
        return (False, None, '')
    c = d.contract
    if dtype == 'pagamento_acconto':
        return (True, c.deposit_amount, 'Acconto')
    if dtype == 'pagamento_saldo':
        return (True, c.balance_amount, 'Saldo')
    return (True, c.total, 'Importo')


def _get_materials_for_contract(contract):
    """Restituisce lista di dict con deadline + suoi documents."""
    from contracts.models import Deadline, DeadlineStatus
    from shared.models import Document

    deadlines = contract.deadlines.select_related('deadline_template').order_by('due_date')
    deadline_ct = ContentType.objects.get_for_model(Deadline)

    today = date.today()
    materials = []
    for d in deadlines:
        docs = Document.objects.filter(
            content_type=deadline_ct,
            object_id=d.id,
            deleted_at__isnull=True,
        ).order_by('-created_at')

        content_fields = []
        for f in (d.content_schema or []):
            content_fields.append({
                'key': f.get('key'),
                'label': f.get('label', f.get('key')),
                'type': f.get('type', 'short_text'),
                'required': f.get('required', False),
                'help_text': f.get('help_text', ''),
                'value': (d.content_data or {}).get(f.get('key'), ''),
            })

        materials.append({
            'deadline': d,
            'documents': list(docs),
            'has_documents': docs.exists(),
            'is_completed': d.status in [DeadlineStatus.RECEIVED, DeadlineStatus.WAIVED],
            'content_fields': content_fields,
            'needs_content': getattr(d, 'submission_kind', 'file') in ('content', 'both'),
            'content_locked': d.due_date < today,
            # Le scadenze di PAGAMENTO accettano l'upload della contabile del
            # bonifico - UNA volta sola: dopo il primo caricamento l'area
            # sparisce (resta la nota "in attesa di verifica"). Il caricamento
            # NON le marca "Pagato": resta compito della segreteria dopo la
            # verifica dell'accredito (vedi material_upload_view).
            'needs_file': (
                getattr(d, 'submission_kind', 'file') in ('file', 'both')
                and (d.deadline_type or '') != 'scadenza_opzione'
                and not ((d.deadline_type or '').startswith('pagamento')
                         and docs.exists())
            ),
            'is_physical': getattr(d, 'submission_kind', '') == 'physical',
            'shipping_instructions': (
                d.deadline_template.shipping_instructions
                if d.deadline_template and getattr(d.deadline_template, 'shipping_instructions', None)
                else ''
            ),
            # File "modello" da scaricare (se l'operatore l'ha allegato al template)
            'template_file_name': (
                d.deadline_template.client_template_file.name.rsplit('/', 1)[-1]
                if d.deadline_template and getattr(
                    d.deadline_template, 'client_template_file', None)
                else None
            ),
        })
        # importo pagamento (vista contratto)
        _ip, _ia, _il = _payment_info(d)
        materials[-1]['is_payment'] = _ip
        materials[-1]['payment_amount'] = _ia
        materials[-1]['payment_label'] = _il

    return materials


# ============================================================================
# View: lista materiali per un contratto
# ============================================================================

@sponsor_required
def materials_view(request, contract_id):
    """Pagina materiali di un contratto: scadenze + upload."""
    from contracts.models import Contract

    contract = get_object_or_404(
        Contract.objects.select_related('event', 'sponsor'),
        id=contract_id,
        deleted_at__isnull=True,
    )

    if contract.sponsor_id != request.sponsor.id:
        return HttpResponseForbidden("Accesso negato.")

    from contracts.models import ContractStatus
    if contract.status == ContractStatus.DRAFT:
        return HttpResponseForbidden("Contratto non disponibile.")
    if contract.status == ContractStatus.CANCELLED:
        return HttpResponseForbidden("Questo contratto è stato annullato.")

    materials = _get_materials_for_contract(contract)

    # Statistiche
    total_count = len(materials)
    completed_count = sum(1 for m in materials if m['is_completed'])
    overdue_count = sum(
        1 for m in materials
        if m['deadline'].is_overdue and not m['is_completed']
    )

    return render(request, 'portal/materials/list.html', {
        'contract': contract,
        'materials': materials,
        'total_count': total_count,
        'completed_count': completed_count,
        'overdue_count': overdue_count,
        'max_upload_mb': DEFAULT_MAX_UPLOAD_SIZE_MB,
    })


# ============================================================================
# View: upload materiale per una deadline
# ============================================================================

@sponsor_required
@require_POST
@transaction.atomic
def material_upload_view(request, deadline_id):
    """
    Upload di uno o più file collegati a una specifica Deadline.
    Marca la deadline come RECEIVED se almeno un file viene caricato.
    """
    from contracts.models import Deadline, DeadlineStatus
    from shared.models import Document

    deadline = get_object_or_404(
        Deadline.objects.select_related('contract', 'deadline_template'),
        id=deadline_id,
    )

    if deadline.contract.sponsor_id != request.sponsor.id:
        return HttpResponseForbidden("Accesso negato.")

    if deadline.status == DeadlineStatus.WAIVED:
        messages.warning(
            request,
            "Questa scadenza è stata esonerata e non richiede materiali."
        )
        return redirect('portal:materials_list', contract_id=deadline.contract_id)

    if deadline.status == DeadlineStatus.RECEIVED:
        messages.warning(
            request,
            "Questa scadenza è già stata consegnata. Per modifiche contatta la segreteria."
        )
        return redirect('portal:materials_list', contract_id=deadline.contract_id)

    # Scadenza di PAGAMENTO con contabile gia' caricata: un solo invio
    # consentito, poi tocca alla segreteria (verifica accredito).
    if (deadline.deadline_type or '').startswith('pagamento'):
        _dl_ct = ContentType.objects.get_for_model(Deadline)
        from shared.models import Document as _Document
        if _Document.objects.filter(
                content_type=_dl_ct, object_id=deadline.id,
                deleted_at__isnull=True).exists():
            messages.warning(
                request,
                "La contabile è già stata inviata ed è in verifica presso la "
                "segreteria. Per modifiche o integrazioni contatta la segreteria."
            )
            return redirect('portal:materials_list', contract_id=deadline.contract_id)

    files = request.FILES.getlist('files')
    if not files:
        messages.error(request, "Nessun file selezionato.")
        return redirect('portal:materials_list', contract_id=deadline.contract_id)

    template = deadline.deadline_template
    max_size_bytes = (
        getattr(template, 'max_file_size_mb', None) or DEFAULT_MAX_UPLOAD_SIZE_MB
    ) * 1024 * 1024

    allowed_mimes = (
        getattr(template, 'allowed_mime_types', None) or DEFAULT_ALLOWED_MIME_TYPES
    )

    # Limita a max 10 file per upload
    files = files[:10]

    deadline_ct = ContentType.objects.get_for_model(Deadline)
    uploaded_count = 0
    errors = []

    for f in files:
        if f.size > max_size_bytes:
            errors.append(
                f"'{f.name}': troppo grande "
                f"({f.size / 1024 / 1024:.1f} MB > {max_size_bytes / 1024 / 1024:.0f} MB)"
            )
            continue

        from pathlib import PurePosixPath
        ext = PurePosixPath(f.name).suffix.lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            errors.append(f"'{f.name}': estensione non consentita ({ext or 'nessuna'})")
            continue

        mime_type = (
            f.content_type
            or mimetypes.guess_type(f.name)[0]
            or 'application/octet-stream'
        )
        if allowed_mimes and mime_type not in allowed_mimes:
            errors.append(f"'{f.name}': tipo non consentito ({mime_type})")
            continue

        try:
            # Nome su disco RANDOMIZZATO (il nome originale resta visibile
            # in Document.file_name): path non indovinabile e nessun rischio
            # da nomi file ostili.
            import uuid as _uuid
            stored_name = f"{_uuid.uuid4().hex}{ext}"
            relative_path = (
                f"documents/contracts/{deadline.contract_id}/"
                f"deadlines/{deadline.id}/{stored_name}"
            )
            saved_path = default_storage.save(relative_path, f)

            Document.objects.create(
                content_type=deadline_ct,
                object_id=deadline.id,
                title=f.name,
                file_name=f.name,
                file_size_bytes=f.size,
                mime_type=mime_type,
                storage_url=settings.MEDIA_URL + saved_path,
                document_type='sponsor_material',
                uploaded_by_user=request.user,
            )
            uploaded_count += 1
            logger.info(
                "Material uploaded: deadline=%s file=%s by user=%s",
                deadline.id, f.name, request.user.id
            )
        except Exception as e:
            logger.exception("Errore upload file %s", f.name)
            errors.append(f"'{f.name}': errore di salvataggio")

    # Scadenze di PAGAMENTO: il file caricato e' la contabile del bonifico.
    # NON marcare "Ricevuto/Pagato" (lo fa la segreteria dopo aver verificato
    # l'accredito, registrando l'incasso): avvisa solo l'amministrazione.
    is_pagamento = (deadline.deadline_type or '').startswith('pagamento')

    if uploaded_count > 0 and is_pagamento:
        try:
            from contracts.tasks.notifications import (
                send_payment_receipt_uploaded_alert,
            )
            send_payment_receipt_uploaded_alert.delay(str(deadline.id))
        except Exception:
            logger.exception(
                "Notifica contabile pagamento non inviata per deadline %s",
                deadline.id)

    if uploaded_count > 0 and not is_pagamento and deadline.status != DeadlineStatus.RECEIVED:
        deadline.mark_as_received(contact=getattr(request, 'contact', None))
        # Contratto firmato caricato: avvisa subito l'amministrazione
        if deadline.deadline_type == 'contratto_firmato':
            try:
                from contracts.tasks.notifications import (
                    send_signed_contract_uploaded_alert,
                )
                send_signed_contract_uploaded_alert.delay(str(deadline.id))
            except Exception:
                logger.exception(
                    "Notifica contratto firmato non inviata per deadline %s",
                    deadline.id)

    if uploaded_count > 0:
        if is_pagamento:
            messages.success(
                request,
                f"✓ Caricati {uploaded_count} file. Grazie: la segreteria "
                "verificherà l'accredito e aggiornerà lo stato del pagamento."
            )
        else:
            messages.success(
                request,
                f"✓ Caricati {uploaded_count} file. "
                f"La scadenza '{deadline.title}' è stata marcata come consegnata."
            )
    if errors:
        for err in errors:
            messages.error(request, err)

    return redirect('portal:materials_list', contract_id=deadline.contract_id)


# ============================================================================
# View: download di un documento
# ============================================================================

@sponsor_required
def material_download_view(request, document_id):
    """Download di un documento (con verifica accesso)."""
    from shared.models import Document
    from contracts.models import Deadline

    document = get_object_or_404(
        Document.objects.filter(deleted_at__isnull=True),
        id=document_id,
    )

    deadline_ct = ContentType.objects.get_for_model(Deadline)
    if document.content_type != deadline_ct:
        return HttpResponseForbidden("Documento non scaricabile.")

    try:
        deadline = Deadline.objects.select_related('contract').get(id=document.object_id)
    except Deadline.DoesNotExist:
        raise Http404()

    if deadline.contract.sponsor_id != request.sponsor.id:
        return HttpResponseForbidden("Accesso negato.")

    relative_path = document.storage_url.replace(settings.MEDIA_URL, '')
    if not default_storage.exists(relative_path):
        raise Http404("File non trovato sul server.")

    response = FileResponse(
        default_storage.open(relative_path, 'rb'),
        as_attachment=True,
        filename=document.file_name,
    )
    return response


@sponsor_required
def deadline_template_download_view(request, deadline_id):
    """Download del file 'modello' allegato al Template scadenza: l'operatore lo
    carica una volta e il cliente lo scarica come traccia (es. template grafico
    alla misura giusta, o Excel con le colonne da compilare)."""
    import os
    from contracts.models import Deadline

    deadline = get_object_or_404(
        Deadline.objects.select_related('contract', 'deadline_template'),
        id=deadline_id,
    )
    if deadline.contract.sponsor_id != request.sponsor.id:
        return HttpResponseForbidden("Accesso negato.")

    tpl = deadline.deadline_template
    if not tpl or not getattr(tpl, 'client_template_file', None):
        raise Http404("Nessun modello disponibile per questa scadenza.")

    f = tpl.client_template_file
    if not default_storage.exists(f.name):
        raise Http404("File non trovato sul server.")

    return FileResponse(
        default_storage.open(f.name, 'rb'),
        as_attachment=True,
        filename=os.path.basename(f.name),
    )


# ============================================================================
# View: delete di un documento
# ============================================================================

@sponsor_required
@require_POST
@transaction.atomic
def material_delete_view(request, document_id):
    """
    Cancella (soft delete) un documento.
    Se era l'unico documento per la deadline, rimette la deadline a PENDING.
    """
    from shared.models import Document
    from contracts.models import Deadline, DeadlineStatus

    document = get_object_or_404(
        Document.objects.filter(deleted_at__isnull=True),
        id=document_id,
    )

    deadline_ct = ContentType.objects.get_for_model(Deadline)
    if document.content_type != deadline_ct:
        return HttpResponseForbidden("Operazione non consentita.")

    try:
        deadline = Deadline.objects.select_related('contract').get(id=document.object_id)
    except Deadline.DoesNotExist:
        raise Http404()

    if deadline.contract.sponsor_id != request.sponsor.id:
        return HttpResponseForbidden("Accesso negato.")

    # Modifiche bloccate dal portale: i file inviati si rimuovono solo dalla segreteria (admin).
    messages.warning(
        request,
        "Per rimuovere un file inviato, contatta la segreteria."
    )
    return redirect('portal:materials_list', contract_id=deadline.contract_id)

    document.deleted_at = timezone.now()
    document.save(update_fields=['deleted_at', 'updated_at'])

    other_docs = Document.objects.filter(
        content_type=deadline_ct,
        object_id=deadline.id,
        deleted_at__isnull=True,
    ).exclude(id=document.id)

    if not other_docs.exists() and deadline.status == DeadlineStatus.RECEIVED:
        deadline.status = DeadlineStatus.PENDING
        deadline.received_at = None
        deadline.save(update_fields=['status', 'received_at', 'updated_at'])

    messages.success(request, f"File '{document.file_name}' rimosso.")
    return redirect('portal:materials_list', contract_id=deadline.contract_id)


# ============================================================================
# View: salvataggio campi compilati dal cliente
# ============================================================================

@sponsor_required
@require_POST
@transaction.atomic
def material_content_view(request, deadline_id):
    """Salva i campi di testo compilati dal cliente per una Deadline."""
    from contracts.models import Deadline, DeadlineStatus

    deadline = get_object_or_404(
        Deadline.objects.select_related('contract'),
        id=deadline_id,
    )
    if deadline.contract.sponsor_id != request.sponsor.id:
        return HttpResponseForbidden("Accesso negato.")
    if deadline.status == DeadlineStatus.WAIVED:
        messages.warning(request, "Questa richiesta e' stata esonerata.")
        return redirect('portal:materials_list', contract_id=deadline.contract_id)
    if deadline.status == DeadlineStatus.RECEIVED:
        messages.warning(request, "Questi dati sono gia' stati inviati. Per modifiche contatta la segreteria.")
        return redirect('portal:materials_list', contract_id=deadline.contract_id)
    if getattr(deadline, 'submission_kind', 'file') not in ('content', 'both'):
        messages.error(request, "Questa richiesta non prevede dati da compilare.")
        return redirect('portal:materials_list', contract_id=deadline.contract_id)

    if deadline.due_date < date.today():
        messages.error(request, "La scadenza e' passata: i dati non sono piu' modificabili.")
        return redirect('portal:materials_list', contract_id=deadline.contract_id)

    schema = deadline.content_schema or []
    data = dict(deadline.content_data or {})
    missing = []
    for fld in schema:
        key = fld.get('key')
        if not key:
            continue
        val = (request.POST.get('field_' + key) or '').strip()
        data[key] = val
        if fld.get('required') and not val:
            missing.append(fld.get('label', key))

    deadline.content_data = data
    deadline.save(update_fields=['content_data', 'updated_at'])

    if missing:
        messages.error(
            request,
            "Salvato, ma mancano i campi obbligatori: " + ", ".join(missing)
        )
        return redirect('portal:materials_list', contract_id=deadline.contract_id)

    if deadline.status != DeadlineStatus.RECEIVED:
        deadline.mark_as_received(contact=getattr(request, 'contact', None))
    messages.success(request, "Dati salvati per '%s'." % deadline.title)
    return redirect('portal:materials_list', contract_id=deadline.contract_id)


# ============================================================================
# Vista materiali AGGREGATA PER EVENTO (scadenze di tutti i contratti del
# cliente per quell'evento)
# ============================================================================

def _materials_from_deadlines(deadlines):
    """Costruisce la lista materiali da una queryset di Deadline."""
    from contracts.models import Deadline, DeadlineStatus
    from shared.models import Document

    deadline_ct = ContentType.objects.get_for_model(Deadline)
    today = date.today()
    materials = []
    for d in deadlines:
        docs = Document.objects.filter(
            content_type=deadline_ct,
            object_id=d.id,
            deleted_at__isnull=True,
        ).order_by('-created_at')

        content_fields = []
        for fld in (d.content_schema or []):
            content_fields.append({
                'key': fld.get('key'),
                'label': fld.get('label', fld.get('key')),
                'type': fld.get('type', 'short_text'),
                'required': fld.get('required', False),
                'help_text': fld.get('help_text', ''),
                'value': (d.content_data or {}).get(fld.get('key'), ''),
            })

        materials.append({
            'deadline': d,
            'documents': list(docs),
            'has_documents': docs.exists(),
            'is_completed': d.status in [DeadlineStatus.RECEIVED, DeadlineStatus.WAIVED],
            'content_fields': content_fields,
            'needs_content': getattr(d, 'submission_kind', 'file') in ('content', 'both'),
            'content_locked': d.due_date < today,
            # Upload contabile consentito anche sulle scadenze di pagamento,
            # una volta sola (vedi nota in _get_materials_for_contract).
            'needs_file': (
                getattr(d, 'submission_kind', 'file') in ('file', 'both')
                and (d.deadline_type or '') != 'scadenza_opzione'
                and not ((d.deadline_type or '').startswith('pagamento')
                         and docs.exists())
            ),
            'template_file_name': (
                d.deadline_template.client_template_file.name.rsplit('/', 1)[-1]
                if d.deadline_template and getattr(
                    d.deadline_template, 'client_template_file', None)
                else None
            ),
        })
        # importo pagamento (vista evento)
        _ip, _ia, _il = _payment_info(d)
        materials[-1]['is_payment'] = _ip
        materials[-1]['payment_amount'] = _ia
        materials[-1]['payment_label'] = _il
    return materials


@sponsor_required
def event_materials_view(request, event_id):
    """Scadenze/materiali del cliente per UN evento (tutti i suoi contratti)."""
    from contracts.models import Contract, Deadline, DeadlineStatus, ContractStatus
    from events.models import Event

    sponsor = request.sponsor
    event = get_object_or_404(Event, id=event_id)

    contracts = Contract.objects.filter(
        sponsor=sponsor, event_id=event_id, deleted_at__isnull=True,
    ).exclude(status__in=[ContractStatus.DRAFT, ContractStatus.CANCELLED])
    if not contracts.exists():
        return HttpResponseForbidden("Accesso negato.")

    contract_ids = list(contracts.values_list('id', flat=True))
    deadlines = list(Deadline.objects
                     .filter(contract_id__in=contract_ids)
                     .select_related('deadline_template')
                     .order_by('due_date'))

    cat = request.GET.get('cat')

    def _is_admin(d):
        t = (d.deadline_type or '').lower()
        title = (d.title or '').lower()
        if t.startswith('pagament') or t == 'scadenza_opzione':
            return True
        kw = ('pagament', 'acconto', 'caparra', 'saldo', 'fattura', 'bonifico', 'opzione')
        return any(k in t for k in kw) or any(k in title for k in kw)

    if cat == 'amm':
        deadlines = [d for d in deadlines if _is_admin(d)]
    elif cat == 'tec':
        deadlines = [d for d in deadlines if not _is_admin(d)]
    else:
        cat = None

    materials = _materials_from_deadlines(deadlines)

    total_count = len(materials)
    completed_count = sum(1 for m in materials if m['is_completed'])
    overdue_count = sum(
        1 for m in materials
        if m['deadline'].is_overdue and not m['is_completed']
    )

    category_label = {'amm': 'Amministrative', 'tec': 'Tecniche'}.get(cat, '')

    return render(request, 'portal/materials/list.html', {
        'event': event,
        'event_mode': True,
        'materials': materials,
        'total_count': total_count,
        'completed_count': completed_count,
        'overdue_count': overdue_count,
        'category': cat,
        'category_label': category_label,
        'max_upload_mb': DEFAULT_MAX_UPLOAD_SIZE_MB,
    })
