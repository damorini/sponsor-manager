"""Duplicazione di un evento per una nuova edizione.

I congressi sono ricorrenti: ogni anno si ricreavano a mano (o via import
Excel) evento, servizi, varianti, template scadenze, stand e blocchi.
`duplica_evento` clona tutta la struttura in un colpo; NON tocca in alcun
modo l'evento di origine ne' i suoi contratti/sponsor.

Cosa viene clonato:
- Event (stato riportato a PLANNING, slug/codice resi unici con suffisso;
  le date restano quelle originali, da aggiornare a mano per la nuova edizione)
- StandBlock e Stand (stato riportato a 'available')
- Service con ServiceVariant, DeadlineTemplate e ServiceInclusion
Cosa NON viene clonato (di proposito): contratti, pagamenti, scadenze,
documenti, comunicazioni - appartengono all'edizione originale.
"""
from django.db import transaction


def _campi_clonabili(obj, escludi=()):
    """Dict {campo: valore} dei campi concreti clonabili (no pk/timestamps)."""
    out = {}
    for f in obj._meta.concrete_fields:
        if f.primary_key or f.name in ('created_at', 'updated_at') or f.name in escludi:
            continue
        out[f.name] = getattr(obj, f.name)
    return out


def _slug_unico(base):
    from events.models import Event
    candidato = f"{base}-copia"
    n = 2
    while Event.objects.filter(slug=candidato).exists():
        candidato = f"{base}-copia{n}"
        n += 1
    return candidato


@transaction.atomic
def duplica_evento(evento):
    """Clona l'evento con tutta la struttura. Ritorna il nuovo Event."""
    from events.models import Event, EventStatus
    from catalog.models import Service, ServiceVariant, ServiceInclusion, DeadlineTemplate
    from venues.models import Stand, StandBlock

    # --- Event ---
    dati = _campi_clonabili(evento, escludi=('slug',))
    nome = dati.get('name')
    if isinstance(nome, dict):
        dati['name'] = {k: f"{v} (copia)" for k, v in nome.items() if v}
    if dati.get('code'):
        dati['code'] = f"{dati['code']}COPIA"[:50]
    dati['status'] = EventStatus.PLANNING
    nuovo = Event(**dati)
    nuovo.slug = _slug_unico(evento.slug or 'evento')
    nuovo.save()

    # --- Service (+ varianti, template scadenze) ---
    # PRIMA degli stand: la creazione di uno Stand auto-genera il servizio
    # "pacchetto spazio espositivo" sull'evento - clonando i servizi dopo,
    # la copia dello stesso servizio dall'originale collide (code unico per
    # evento). Idempotente sul code per lo stesso motivo.
    mappa_servizi = {}
    for srv in Service.objects.filter(event=evento):
        esistente = (Service.objects.filter(event=nuovo, code=srv.code).first()
                     if srv.code else None)
        if esistente is not None:
            mappa_servizi[srv.pk] = esistente
            continue
        nuovo_srv = Service(**{**_campi_clonabili(srv), 'event': nuovo})
        nuovo_srv.save()
        mappa_servizi[srv.pk] = nuovo_srv
        for var in ServiceVariant.objects.filter(service=srv):
            ServiceVariant(**{**_campi_clonabili(var), 'service': nuovo_srv}).save()
        for tpl in DeadlineTemplate.objects.filter(service=srv):
            DeadlineTemplate(**{**_campi_clonabili(tpl), 'service': nuovo_srv}).save()

    # --- StandBlock e Stand ---
    mappa_blocchi = {}
    for blocco in StandBlock.objects.filter(event=evento):
        b = StandBlock(**{**_campi_clonabili(blocco), 'event': nuovo})
        if hasattr(b, 'status'):
            b.status = 'available'
        b.save()
        mappa_blocchi[blocco.pk] = b
    for stand in Stand.objects.filter(event=evento):
        s_dati = _campi_clonabili(stand)
        s_dati['event'] = nuovo
        if s_dati.get('stand_block') is not None:
            s_dati['stand_block'] = mappa_blocchi.get(stand.stand_block_id)
        s_dati['status'] = 'available'
        Stand(**s_dati).save()

    # --- ServiceInclusion (parent e child rimappati sui cloni) ---
    for inc in ServiceInclusion.objects.filter(parent__event=evento):
        parent_clone = mappa_servizi.get(inc.parent_id)
        child_clone = mappa_servizi.get(inc.child_id)
        if parent_clone and child_clone:
            ServiceInclusion.objects.create(
                parent=parent_clone, child=child_clone, quantity=inc.quantity)

    return nuovo
