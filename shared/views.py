"""Serving PROTETTO dei file caricati (media/documents/...).

In produzione Caddy inoltra /media/documents/* a Django (vedi Caddyfile)
invece di servirli come file statici: i documenti degli sponsor (contabili
bonifico, contratti firmati, materiali) non devono essere scaricabili da
chiunque indovini l'URL — gli id sono nei path e i nomi file prevedibili.

Regole di accesso:
- staff: sempre;
- utente sponsor: solo i documenti collegati a un contratto/scadenza/anagrafica
  di una delle SUE aziende (multi-azienda: basta una qualsiasi);
- tutti gli altri: 404 (non riveliamo nemmeno che il file esiste).

I file vengono serviti come allegato (Content-Disposition: attachment), mai
renderizzati inline: cosi' un eventuale HTML/SVG caricato non puo' eseguire
script nel dominio del portale.
"""
import posixpath
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404


def _sponsor_ids_for_user(user):
    """Tutte le aziende collegate all'utente portale (FK multi-azienda)."""
    try:
        return set(user.contact_profiles.values_list('sponsor_id', flat=True))
    except Exception:
        return set()


def _document_sponsor_id(doc):
    """Sponsor proprietario del documento, risolvendo il collegamento
    polimorfico (Contract / Deadline / Sponsor). None se non riconducibile."""
    target = (doc.content_type.model or '').lower() if doc.content_type_id else ''
    if target == 'contract':
        from contracts.models import Contract
        return (Contract.all_objects.filter(pk=doc.object_id)
                .values_list('sponsor_id', flat=True).first())
    if target == 'deadline':
        from contracts.models import Deadline
        return (Deadline.objects.filter(pk=doc.object_id)
                .values_list('contract__sponsor_id', flat=True).first())
    if target == 'sponsor':
        return doc.object_id
    return None


@login_required
def protected_document_media(request, subpath):
    """Serve un file sotto media/documents/ SOLO a staff o allo sponsor
    proprietario. Mappa il path richiesto sul record Document tramite
    storage_url (come salvato all'upload/generazione)."""
    from shared.models import Document

    rel = posixpath.normpath('documents/' + subpath)
    if not rel.startswith('documents/') or '..' in rel.split('/'):
        raise Http404

    url = settings.MEDIA_URL + rel
    doc = Document.objects.filter(storage_url=url, deleted_at__isnull=True).first()
    if doc is None:
        raise Http404

    if not request.user.is_staff:
        # Documenti marcati "solo interno" dalla segreteria: mai al cliente,
        # nemmeno se il path e' suo (stesso criterio delle liste del portale).
        if not doc.is_visible_to_sponsor:
            raise Http404
        sponsor_id = _document_sponsor_id(doc)
        if sponsor_id is None or sponsor_id not in _sponsor_ids_for_user(request.user):
            raise Http404

    full = Path(settings.MEDIA_ROOT) / rel
    if not full.exists():
        raise Http404
    return FileResponse(
        open(full, 'rb'),
        as_attachment=True,
        filename=doc.file_name or full.name,
    )
