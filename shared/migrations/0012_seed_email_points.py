from django.db import migrations

# 12 punti di invio × 2 tipi evento = 24 righe (inattive: finché non attivate,
# viene usato il testo email standard di sistema).
POINTS = [
    ('portal_invitation', 'Invito al portale'),
    ('quote_email', 'Invio preventivo'),
    ('contract_signed', 'Conferma preventivo — domanda di ammissione'),
    ('sponsor_contract_email', 'Conferma preventivo — contratto di sponsorizzazione'),
    ('payment_confirmation', 'Conferma pagamento ricevuto'),
    ('deadline_reminder', 'Reminder scadenza'),
    ('deadline_overdue', 'Sollecito scadenza scaduta'),
    ('option_reminder', 'Reminder opzione spazio'),
    ('cart_recovery', 'Recupero carrello abbandonato'),
    ('operator_alert', 'Alert operatore (interno)'),
    ('password_reset', 'Reset password'),
    ('portal_message_notification', 'Notifica nuovo messaggio nel portale'),
]
EVENT_TYPES = [('ECM', 'ECM'), ('NON_ECM', 'Non ECM')]


def seed(apps, schema_editor):
    EmailTemplate = apps.get_model('shared', 'EmailTemplate')
    for code, label in POINTS:
        for et_code, et_label in EVENT_TYPES:
            EmailTemplate.objects.get_or_create(
                code=code,
                event_type=et_code,
                defaults={
                    'name': f"{label} — {et_label}",
                    'description': (
                        "Modello personalizzabile per questo punto di invio e tipo "
                        "evento. Attivalo e compila oggetto e corpo per usarlo al "
                        "posto dell'email standard."
                    ),
                    'communication_type': 'manual',
                    'subject_template': {},
                    'body_template': {},
                    'language': 'it',
                    'is_active': False,
                },
            )


def unseed(apps, schema_editor):
    EmailTemplate = apps.get_model('shared', 'EmailTemplate')
    codes = [c for c, _ in POINTS]
    EmailTemplate.objects.filter(
        code__in=codes, event_type__in=['ECM', 'NON_ECM'], is_active=False
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('shared', '0011_emailtemplate_event_type'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
