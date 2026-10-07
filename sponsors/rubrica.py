"""Logica della rubrica contatti: destinatari delle campagne per area,
trasferimento ad altra azienda, anonimizzazione GDPR."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.functions import Lower
from django.utils import timezone

from sponsors.models import Contact, SuppressedEmail


def contatti_raggiungibili():
    """Contatti a cui si puo' scrivere per marketing: non cestinati, azienda
    non cestinata, non usciti dall'azienda, con email, non disiscritti."""
    return (Contact.objects
            .filter(sponsor__deleted_at__isnull=True, left_company_at__isnull=True)
            .exclude(email='')
            .annotate(email_l=Lower('email'))
            .exclude(email_l__in=SuppressedEmail.objects.values('email')))


def destinatari_per_aree(aree):
    """Un contatto per indirizzo email (la stessa persona su piu' aziende o
    piu' aree riceve UNA sola email), ordinati per email."""
    qs = (contatti_raggiungibili()
          .filter(interest_areas__in=aree)
          .select_related('sponsor')
          .order_by('email_l', 'created_at'))
    visti, out = set(), []
    for c in qs:
        if c.email_l in visti:
            continue
        visti.add(c.email_l)
        out.append(c)
    return out


@transaction.atomic
def trasferisci_contatto(contact, nuovo_sponsor, nuova_email='', data=None):
    """La persona cambia azienda: crea un NUOVO contatto nella nuova azienda e
    segna il vecchio come uscito. Il vecchio non si sposta mai: i contratti
    firmati (Contract.sponsor_signer_contact) devono restare intestati a chi
    lavorava li' allora. Ritorna il nuovo contatto."""
    if contact.left_company_at:
        raise ValidationError("Questo contatto è già segnato come uscito dall'azienda.")
    if nuovo_sponsor.pk == contact.sponsor_id:
        raise ValidationError("La nuova azienda è uguale a quella attuale.")
    data = data or timezone.localdate()
    nuovo = Contact(
        sponsor=nuovo_sponsor,
        first_name=contact.first_name, last_name=contact.last_name,
        email=(nuova_email or contact.email).strip(),
        phone=contact.phone, job_title=contact.job_title,
        preferred_language=contact.preferred_language,
        marketing_consent=contact.marketing_consent,
        marketing_consent_at=contact.marketing_consent_at,
        notes=f"Trasferito da {contact.sponsor.legal_name} il {data:%d/%m/%Y}.",
    )
    nuovo.full_clean()
    nuovo.save()
    nuovo.interest_areas.set(contact.interest_areas.all())

    contact.left_company_at = data
    contact.is_primary = False
    contact.has_portal_access = False
    contact.portal_user = None
    contact.save()
    return nuovo


ANON_NOME = 'Anonimizzato'


@transaction.atomic
def anonimizza_persona(email):
    """Richiesta GDPR di cancellazione: anonimizza TUTTE le schede con questa
    email (anche cestinate), le cestina e mette l'indirizzo tra le email
    escluse, cosi' un import futuro non la reinserisce. Le righe restano per
    non rompere i contratti che le citano."""
    from shared.models import AuditLog
    email = (email or '').strip()
    if not email:
        raise ValidationError("Email mancante: impossibile identificare la persona da anonimizzare.")
    SuppressedEmail.add(email, SuppressedEmail.Reason.ANONYMIZED)
    schede = list(Contact.all_objects.filter(email__iexact=email))
    adesso = timezone.now()
    for c in schede:
        c.portal_user = None          # prima di save(): save() riallinea l'email dell'utente collegato
        c.has_portal_access = False
        c.first_name, c.last_name, c.full_name = ANON_NOME, '', ''
        c.email = f'anonimizzato-{c.pk}@invalid.invalid'
        c.phone = c.job_title = c.notes = ''
        c.signer_tax_code = c.birth_place = c.birth_province = ''
        c.residence_street = c.residence_street_number = c.residence_city = ''
        c.residence_zip = c.residence_province = c.id_document_number = ''
        c.birth_date = None
        c.is_primary = c.is_signer = c.marketing_consent = False
        c.marketing_consent_at = None
        c.deleted_at = c.deleted_at or adesso
        c.save()
        c.interest_areas.clear()
        # lo storico modifiche dal portale conteneva i vecchi valori in chiaro
        AuditLog.objects.filter(entity_type='Contact', entity_id=c.pk).update(changes=None)
    return len(schede)
