"""Promemoria e solleciti delle scadenze di pagamento: accanto all'importo la
nota IVA del contratto ({{ nota_iva }}) al posto di "(IVA inclusa)" fisso,
cosi' i clienti esenti vedono il motivo dell'esenzione."""
from django.db import migrations

CODICI = ("deadline_reminder", "deadline_overdue")
VECCHI = ("(IVA inclusa)", "(VAT incl.)", "(VAT included)")


def avanti(apps, schema_editor):
    EmailTemplate = apps.get_model("shared", "EmailTemplate")
    for t in EmailTemplate.objects.filter(code__in=CODICI):
        corpo = dict(t.body_template or {})
        cambiato = False
        for lingua, testo in corpo.items():
            nuovo = testo or ""
            for v in VECCHI:
                nuovo = nuovo.replace(v, "{{ nota_iva }}")
            if nuovo != (testo or ""):
                corpo[lingua] = nuovo
                cambiato = True
        if cambiato:
            t.body_template = corpo
            t.save(update_fields=["body_template"])


def indietro(apps, schema_editor):
    EmailTemplate = apps.get_model("shared", "EmailTemplate")
    for t in EmailTemplate.objects.filter(code__in=CODICI):
        corpo = dict(t.body_template or {})
        for lingua, testo in corpo.items():
            corpo[lingua] = (testo or "").replace(
                "{{ nota_iva }}", "(VAT incl.)" if lingua == "en" else "(IVA inclusa)")
        t.body_template = corpo
        t.save(update_fields=["body_template"])


class Migration(migrations.Migration):
    dependencies = [
        ("shared", "0017_alter_communication_communication_type_and_more"),
    ]
    operations = [migrations.RunPython(avanti, indietro)]
