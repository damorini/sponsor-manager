"""Logica della rubrica contatti: destinatari delle campagne per area,
trasferimento ad altra azienda, anonimizzazione GDPR."""
from django.db.models.functions import Lower

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
