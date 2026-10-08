# Rubrica contatti con aree di interesse — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trasformare l'anagrafica contatti dello Sponsor Manager nella rubrica condivisa di VALET: aree di interesse per persona, import da Excel/CSV con anteprima, campagne email per area con disiscrizione globale, trasferimento di un contatto ad altra azienda e anonimizzazione GDPR.

**Architecture:** Tutto vive nell'app `sponsors` (modelli `InterestArea`, `SuppressedEmail`, `InterestCampaign` + 2 campi su `Contact`). La logica sta in due moduli puri e testabili: `sponsors/rubrica.py` (destinatari, trasferimento, anonimizzazione) e `sponsors/rubrica_import.py` (lettura file, analisi, applicazione). L'invio riusa `send_email` e il template `promotional_campaign` gia' usati dalle campagne evento; la disiscrizione e' per INDIRIZZO email (tabella `SuppressedEmail`) e vale per tutte le campagne promozionali, comprese quelle per evento esistenti.

**Tech Stack:** Django 5.1, PostgreSQL, Celery, openpyxl, pytest-django.

## Global Constraints

- Decisioni dell'utente (Daniele, 08/10/2026), da NON rimettere in discussione:
  - le aree di interesse sono **per persona** (Contact), non per azienda; l'azienda "eredita" l'unione delle aree dei suoi contatti (solo visualizzazione);
  - i contatti importati sono **gia' consensati**: le campagne vanno a **tutti tranne i disiscritti** (nessun filtro su `marketing_consent`); l'import registra comunque `marketing_consent=True` + data;
  - i contatti li modifica **tutto lo staff**; l'anonimizzazione GDPR solo superuser / ruolo `admin`;
  - cambio azienda = **nuovo contatto** nella nuova azienda + vecchio segnato "Non più in azienda dal"; mai spostare il contatto (i contratti firmati puntano a lui via `Contract.sponsor_signer_contact`);
  - la cancellazione resta il soft delete esistente (`SoftDeleteModel`).
- Colonne del file utente: `company, referente, email, ruolo, tel` + nuova `interessi` (valori separati da `;`). Opzionali `nome`, `cognome` (se presenti vincono su `referente`).
- Mai unire aziende in silenzio: nome azienda simile-ma-diverso = riga in errore, l'operatore corregge il file.
- Area sconosciuta nel file = riga in errore (mai creare aree dall'import).
- Testi UI in italiano, commit in italiano brevi e descrittivi (stile repo), con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Il working tree contiene WIP altrui NON nostro: `contracts/models.py`, `venues/models.py`, `contracts/occupazione.py`, `tests/test_spazio_occupato_da_bozza.py`, `venues/management/`. Non toccarli, non stagearli. Mai `git add -A` / `git add .`: solo percorsi espliciti, poi `git diff --cached --stat` prima di ogni commit.
- Comandi: tutti dentro WSL, `cd ~/progetti/sponsor_manager && source venv/bin/activate` (postgres e redis avviati: `sudo service postgresql start && sudo service redis-server start`). Messaggi di commit scritti con lo strumento Write in un file e passati con `git commit -F`, poi verificati con `git log -1 --format=%B`.
- Template Django: ogni `{#` chiuso sulla stessa riga (`grep -rn '{#' <file> | grep -v '#}'` deve dare 0 righe); `{% trans %}` solo con `{% load i18n %}`.
- Nessun deploy in produzione senza OK esplicito di Daniele (Task 9).

## File Structure

| File | Ruolo |
|---|---|
| `sponsors/models.py` (modifica) | `InterestArea`, `SuppressedEmail`, `InterestCampaign`; su `Contact`: `interest_areas`, `left_company_at` |
| `sponsors/migrations/0020_rubrica.py` (nuovo, generato) | migrazione dei modelli sopra |
| `sponsors/rubrica.py` (nuovo) | `destinatari_per_aree`, `trasferisci_contatto`, `anonimizza_persona` |
| `sponsors/rubrica_import.py` (nuovo) | `leggi_file`, `analizza`, `applica`, `RigaImport` |
| `sponsors/admin.py` (modifica) | admin aree, campagne, email escluse; su ContactAdmin: campi, filtri, viste import/trasferisci/anonimizza |
| `sponsors/templates/admin/sponsors/contact/*.html` (nuovi) | pagine import, trasferisci, anonimizza, pulsante in lista |
| `events/models.py:418-436` (modifica) | campagne evento escludono email disiscritte e contatti usciti |
| `contracts/tasks/notifications.py` (modifica, in coda al file) | task `send_interest_campaign` |
| `portal/views/campaigns.py`, `portal/urls.py`, `portal/templates/portal/campaign_unsubscribe.html` (modifica) | disiscrizione globale marketing |
| `tests/test_rubrica_*.py` (nuovi) | test |

---

### Task 1: Modelli e migrazione

**Files:**
- Modify: `sponsors/models.py` (prima di `class Contact`, dentro `Contact`, in fondo al file)
- Create: `sponsors/migrations/0020_rubrica.py` (generata)
- Test: `tests/test_rubrica_modelli.py`

**Interfaces:**
- Produces: `InterestArea(name, is_active)`; `Contact.interest_areas` (M2M, related_name `contacts`); `Contact.left_company_at` (DateField null); `SuppressedEmail(email, reason)` con `SuppressedEmail.Reason.UNSUBSCRIBED/ANONYMIZED`, `SuppressedEmail.add(email, reason) -> SuppressedEmail`, `SuppressedEmail.is_suppressed(email) -> bool`; `InterestCampaign(name, subject, body, interest_areas, sent_at, sent_by, sent_count)`.

- [ ] **Step 1: Scrivere i test che falliscono**

```python
# tests/test_rubrica_modelli.py
"""Rubrica: aree di interesse, email escluse dal marketing."""
import pytest
from django.db import IntegrityError


@pytest.mark.django_db
class TestInterestArea:
    def test_nome_unico_senza_distinzione_maiuscole(self):
        from sponsors.models import InterestArea
        InterestArea.objects.create(name='Cardiologia')
        with pytest.raises(IntegrityError):
            InterestArea.objects.create(name='cardiologia')

    def test_contatto_con_piu_aree(self, contact):
        from sponsors.models import InterestArea
        a = InterestArea.objects.create(name='Cardiologia')
        b = InterestArea.objects.create(name='Oncologia')
        contact.interest_areas.set([a, b])
        assert set(contact.interest_areas.values_list('name', flat=True)) == {'Cardiologia', 'Oncologia'}


@pytest.mark.django_db
class TestSuppressedEmail:
    def test_add_normalizza_e_non_duplica(self):
        from sponsors.models import SuppressedEmail
        SuppressedEmail.add('  Mario.Rossi@Esempio.IT ', SuppressedEmail.Reason.UNSUBSCRIBED)
        SuppressedEmail.add('mario.rossi@esempio.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        assert SuppressedEmail.objects.count() == 1
        assert SuppressedEmail.objects.get().email == 'mario.rossi@esempio.it'

    def test_is_suppressed_case_insensitive(self):
        from sponsors.models import SuppressedEmail
        SuppressedEmail.add('a@b.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        assert SuppressedEmail.is_suppressed('A@B.IT')
        assert not SuppressedEmail.is_suppressed('altro@b.it')

    def test_anonimizzazione_prevale_su_disiscrizione(self):
        from sponsors.models import SuppressedEmail
        SuppressedEmail.add('a@b.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        SuppressedEmail.add('a@b.it', SuppressedEmail.Reason.ANONYMIZED)
        assert SuppressedEmail.objects.get().reason == SuppressedEmail.Reason.ANONYMIZED
        # una disiscrizione successiva NON declassa l'anonimizzazione
        SuppressedEmail.add('a@b.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        assert SuppressedEmail.objects.get().reason == SuppressedEmail.Reason.ANONYMIZED

    def test_add_email_vuota_non_crea_nulla(self):
        from sponsors.models import SuppressedEmail
        assert SuppressedEmail.add('  ', SuppressedEmail.Reason.UNSUBSCRIBED) is None
        assert SuppressedEmail.objects.count() == 0
```

- [ ] **Step 2: Verificare che falliscano**

Run: `pytest tests/test_rubrica_modelli.py -v`
Expected: FAIL con `ImportError: cannot import name 'InterestArea'`

- [ ] **Step 3: Aggiungere i modelli**

In `sponsors/models.py`, in cima aggiungere l'import:

```python
from django.db.models.functions import Lower
```

Subito PRIMA di `class Contact(SoftDeleteModel):` inserire (la riga sopra `class Contact` e' vuota, nessun decoratore):

```python
class InterestArea(TimeStampedModel):
    """Area di interesse (es. Cardiologia): indica a quale tipologia di evento
    e' interessata una PERSONA. Elenco gestito dall'admin, mai testo libero,
    cosi' i filtri delle campagne non perdono contatti per errori di battitura."""
    name = models.CharField(max_length=100, verbose_name="Nome")
    is_active = models.BooleanField(
        default=True, verbose_name="Attiva",
        help_text="Le aree disattivate non compaiono nelle nuove selezioni.")

    class Meta:
        verbose_name = "Area di interesse"
        verbose_name_plural = "Aree di interesse"
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(Lower('name'), name='unique_interestarea_name_ci'),
        ]

    def __str__(self):
        return self.name


```

Dentro `class Contact`, subito dopo il campo `notes = models.TextField(...)` (riga ~315):

```python
    # --- Rubrica ---
    interest_areas = models.ManyToManyField(
        'sponsors.InterestArea',
        blank=True,
        related_name='contacts',
        verbose_name="Aree di interesse",
        help_text="Tipologie di evento che segue QUESTA persona.",
    )
    left_company_at = models.DateField(
        null=True, blank=True,
        verbose_name="Non più in azienda dal",
        help_text="Valorizzato dal trasferimento ad altra azienda: il contatto resta "
                  "per lo storico dei contratti ma non riceve più comunicazioni.",
    )
```

In fondo al file:

```python
class SuppressedEmail(TimeStampedModel):
    """Indirizzi esclusi da TUTTE le campagne promozionali. La disiscrizione
    segue la PERSONA (l'indirizzo), non la scheda contatto: se cambia azienda o
    compare in piu' aziende resta esclusa ovunque. Email salvata minuscola."""

    class Reason(models.TextChoices):
        UNSUBSCRIBED = 'unsubscribed', 'Disiscritto dal marketing'
        ANONYMIZED = 'anonymized', 'Dati cancellati (GDPR)'

    email = models.EmailField(verbose_name="Email")
    reason = models.CharField(
        max_length=20, choices=Reason.choices, verbose_name="Motivo")

    class Meta:
        verbose_name = "Email esclusa dal marketing"
        verbose_name_plural = "Email escluse dal marketing"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(Lower('email'), name='unique_suppressedemail_email_ci'),
        ]

    def __str__(self):
        return f"{self.email} ({self.get_reason_display()})"

    @staticmethod
    def _norm(email):
        return (email or '').strip().lower()

    @classmethod
    def add(cls, email, reason):
        """Registra l'esclusione (idempotente). ANONYMIZED prevale su
        UNSUBSCRIBED e non viene mai declassata."""
        e = cls._norm(email)
        if not e:
            return None
        obj, created = cls.objects.get_or_create(email=e, defaults={'reason': reason})
        if (not created and reason == cls.Reason.ANONYMIZED
                and obj.reason != cls.Reason.ANONYMIZED):
            obj.reason = reason
            obj.save(update_fields=['reason', 'updated_at'])
        return obj

    @classmethod
    def is_suppressed(cls, email):
        e = cls._norm(email)
        return bool(e) and cls.objects.filter(email=e).exists()


class InterestCampaign(TimeStampedModel):
    """Email una tantum a tutti i contatti interessati a una o piu' aree.
    Si invia solo a mano dall'admin (mai dallo scheduler)."""
    name = models.CharField(
        max_length=255, verbose_name="Nome interno",
        help_text="Solo per riconoscerla in lista: il cliente non la vede.")
    interest_areas = models.ManyToManyField(
        'sponsors.InterestArea', related_name='campaigns',
        verbose_name="Aree di interesse",
        help_text="Riceve chi segue ALMENO UNA delle aree scelte.")
    subject = models.JSONField(default=dict, blank=True, verbose_name="Oggetto")
    body = models.JSONField(
        default=dict, blank=True, verbose_name="Corpo email",
        help_text="Segnaposto: {{ contact.first_name }}, {{ contact.full_name }}, "
                  "{{ sponsor.legal_name }}.")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Inviata il")
    sent_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name="Inviata da")
    sent_count = models.PositiveIntegerField(default=0, verbose_name="Email inviate")

    class Meta:
        verbose_name = "Campagna per aree di interesse"
        verbose_name_plural = "Campagne per aree di interesse"
        ordering = ['-created_at']

    def __str__(self):
        return self.name
```

- [ ] **Step 4: Check e migrazione**

Run: `python manage.py check && python manage.py makemigrations sponsors --name rubrica`
Expected: `System check identified no issues`, poi `sponsors/migrations/0020_rubrica.py` con CreateModel InterestArea / SuppressedEmail / InterestCampaign, AddField interest_areas / left_company_at, AddConstraint x2. Aprire il file e verificare che NON contenga operazioni su altre app.

- [ ] **Step 5: Test verdi**

Run: `pytest tests/test_rubrica_modelli.py -v --create-db`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git status --short
git add sponsors/models.py sponsors/migrations/0020_rubrica.py tests/test_rubrica_modelli.py
git diff --cached --stat
git commit -F ~/msg_rubrica.txt   # "Rubrica: aree di interesse per contatto ed email escluse dal marketing"
```

---

### Task 2: Destinatari delle campagne (e campagne evento che rispettano le esclusioni)

**Files:**
- Create: `sponsors/rubrica.py`
- Modify: `events/models.py:418-436` (`eligible_contacts_queryset`)
- Test: `tests/test_rubrica_destinatari.py`

**Interfaces:**
- Consumes: modelli del Task 1.
- Produces: `destinatari_per_aree(aree) -> list[Contact]` (un solo contatto per indirizzo email, ordinati per email).

- [ ] **Step 1: Test che falliscono**

```python
# tests/test_rubrica_destinatari.py
"""Chi riceve una campagna per aree di interesse."""
import pytest
from datetime import date


@pytest.fixture
def aree(db):
    from sponsors.models import InterestArea
    return {n: InterestArea.objects.create(name=n) for n in ('Cardiologia', 'Oncologia')}


def _contatto(azienda, email, nome='Mario Rossi', aree=()):
    from sponsors.models import Sponsor, Contact
    sponsor, _ = Sponsor.objects.get_or_create(legal_name=azienda, defaults={'address_country': 'IT'})
    c = Contact.objects.create(sponsor=sponsor, full_name=nome, email=email)
    c.interest_areas.set(aree)
    return c


@pytest.mark.django_db
class TestDestinatari:
    def test_solo_chi_segue_le_aree_scelte(self, aree):
        from sponsors.rubrica import destinatari_per_aree
        _contatto('A Srl', 'cardio@a.it', aree=[aree['Cardiologia']])
        _contatto('A Srl', 'onco@a.it', nome='Anna Bianchi', aree=[aree['Oncologia']])
        _contatto('A Srl', 'nessuna@a.it', nome='Luca Verdi')
        emails = [c.email for c in destinatari_per_aree([aree['Cardiologia']])]
        assert emails == ['cardio@a.it']

    def test_una_email_una_volta_anche_con_piu_aree_e_aziende(self, aree):
        from sponsors.rubrica import destinatari_per_aree
        _contatto('A Srl', 'mario@x.it', aree=list(aree.values()))
        _contatto('B Srl', 'MARIO@x.it', aree=[aree['Cardiologia']])  # stessa persona, altra azienda
        assert len(destinatari_per_aree(list(aree.values()))) == 1

    def test_esclude_disiscritti(self, aree):
        from sponsors.models import SuppressedEmail
        from sponsors.rubrica import destinatari_per_aree
        _contatto('A Srl', 'via@a.it', aree=[aree['Cardiologia']])
        SuppressedEmail.add('VIA@a.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        assert destinatari_per_aree([aree['Cardiologia']]) == []

    def test_esclude_usciti_cestinati_e_aziende_cestinate(self, aree):
        from sponsors.rubrica import destinatari_per_aree
        uscito = _contatto('A Srl', 'uscito@a.it', aree=[aree['Cardiologia']])
        uscito.left_company_at = date(2026, 1, 1)
        uscito.save()
        _contatto('A Srl', 'cestinato@a.it', nome='Anna Bianchi', aree=[aree['Cardiologia']]).delete()
        c = _contatto('Chiusa Srl', 'chiusa@c.it', nome='Luca Verdi', aree=[aree['Cardiologia']])
        c.sponsor.delete()
        assert destinatari_per_aree([aree['Cardiologia']]) == []


@pytest.mark.django_db
class TestCampagneEventoRispettanoEsclusioni:
    def test_campagna_evento_esclude_email_disiscritta_globalmente(self):
        from contracts.models import Contract, ContractKind, ContractStatus
        from events.models import Event, PromotionalCampaign
        from sponsors.models import SuppressedEmail
        ev = Event.objects.create(name={'it': 'Ev'}, code='EVRUB',
                                  start_date=date(2026, 11, 1), end_date=date(2026, 11, 2))
        c = _contatto('Firmato Srl', 'firmato@f.it')
        Contract.objects.create(sponsor=c.sponsor, event=ev, contract_kind=ContractKind.MAIN,
                                status=ContractStatus.SIGNED, contract_number='RUB-001')
        camp = PromotionalCampaign.objects.create(event=ev, name='x', subject={'it': 's'}, body={'it': 'b'})
        assert camp.eligible_contacts_queryset().count() == 1
        SuppressedEmail.add('firmato@f.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        assert camp.eligible_contacts_queryset().count() == 0
```

- [ ] **Step 2: Verificare che falliscano**

Run: `pytest tests/test_rubrica_destinatari.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'sponsors.rubrica'`

- [ ] **Step 3: Implementare**

```python
# sponsors/rubrica.py
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
```

In `events/models.py`, sostituire il `return` finale di `eligible_contacts_queryset` (righe 433-436):

```python
        from sponsors.rubrica import contatti_raggiungibili
        return (contatti_raggiungibili()
                .filter(sponsor_id__in=sponsor_ids)
                .exclude(id__in=opted_out_ids))
```

e togliere l'ormai inutile `from sponsors.models import Contact` dentro il metodo (riga 424).

- [ ] **Step 4: Test verdi, comprese le campagne evento esistenti**

Run: `pytest tests/test_rubrica_destinatari.py tests/test_campagne_promozionali.py -v`
Expected: tutti passed (le campagne evento non devono regredire)

- [ ] **Step 5: Commit**

```bash
git add sponsors/rubrica.py events/models.py tests/test_rubrica_destinatari.py
git diff --cached --stat
git commit -F ~/msg_rubrica.txt   # "Rubrica: destinatari per area; le campagne evento escludono disiscritti e contatti usciti"
```

---

### Task 3: Trasferimento ad altra azienda e anonimizzazione

**Files:**
- Modify: `sponsors/rubrica.py` (in coda)
- Test: `tests/test_rubrica_trasferimento.py`

**Interfaces:**
- Produces: `trasferisci_contatto(contact, nuovo_sponsor, nuova_email='', data=None) -> Contact` (il NUOVO contatto; solleva `ValidationError`); `anonimizza_persona(email) -> int` (numero di schede anonimizzate).

- [ ] **Step 1: Test che falliscono**

```python
# tests/test_rubrica_trasferimento.py
"""Cambio azienda e cancellazione GDPR di un contatto."""
import pytest
from datetime import date
from django.core.exceptions import ValidationError


@pytest.fixture
def due_aziende(db):
    from sponsors.models import Sponsor
    return (Sponsor.objects.create(legal_name='Vecchia Srl', address_country='IT'),
            Sponsor.objects.create(legal_name='Nuova Spa', address_country='IT'))


@pytest.fixture
def rossi(due_aziende):
    from sponsors.models import Contact, InterestArea
    c = Contact.objects.create(sponsor=due_aziende[0], first_name='Mario', last_name='Rossi',
                               email='mario@vecchia.it', phone='333', job_title='PM',
                               is_primary=True)
    c.interest_areas.set([InterestArea.objects.create(name='Cardiologia')])
    return c


@pytest.mark.django_db
class TestTrasferimento:
    def test_crea_nuovo_contatto_e_segna_il_vecchio(self, rossi, due_aziende):
        from sponsors.rubrica import trasferisci_contatto
        nuovo = trasferisci_contatto(rossi, due_aziende[1], 'mario@nuova.it', date(2026, 10, 1))
        rossi.refresh_from_db()
        assert nuovo.pk != rossi.pk
        assert nuovo.sponsor == due_aziende[1]
        assert (nuovo.full_name, nuovo.email, nuovo.phone) == ('Mario Rossi', 'mario@nuova.it', '333')
        assert list(nuovo.interest_areas.values_list('name', flat=True)) == ['Cardiologia']
        assert rossi.sponsor == due_aziende[0]          # MAI spostato: i contratti restano giusti
        assert rossi.left_company_at == date(2026, 10, 1)
        assert rossi.is_primary is False

    def test_senza_nuova_email_tiene_la_vecchia(self, rossi, due_aziende):
        from sponsors.rubrica import trasferisci_contatto
        assert trasferisci_contatto(rossi, due_aziende[1]).email == 'mario@vecchia.it'

    def test_stessa_azienda_rifiutato(self, rossi, due_aziende):
        from sponsors.rubrica import trasferisci_contatto
        with pytest.raises(ValidationError):
            trasferisci_contatto(rossi, due_aziende[0])

    def test_gia_uscito_rifiutato(self, rossi, due_aziende):
        from sponsors.rubrica import trasferisci_contatto
        trasferisci_contatto(rossi, due_aziende[1])
        with pytest.raises(ValidationError):
            trasferisci_contatto(rossi, due_aziende[1])


@pytest.mark.django_db
class TestAnonimizzazione:
    def test_anonimizza_tutte_le_schede_della_persona(self, rossi, due_aziende):
        from sponsors.models import Contact, SuppressedEmail
        from sponsors.rubrica import anonimizza_persona, trasferisci_contatto
        trasferisci_contatto(rossi, due_aziende[1])     # stessa email su due aziende
        assert anonimizza_persona('MARIO@vecchia.it') == 2
        for c in Contact.all_objects.filter(sponsor__in=due_aziende):
            assert c.full_name == 'Anonimizzato'
            assert c.email.endswith('@invalid.invalid')
            assert (c.phone, c.job_title, c.notes) == ('', '', '')
            assert c.deleted_at is not None
            assert c.interest_areas.count() == 0
        assert SuppressedEmail.objects.get().reason == SuppressedEmail.Reason.ANONYMIZED

    def test_scollega_utente_portale_senza_toccarne_email(self, rossi):
        from users.models import User
        from sponsors.rubrica import anonimizza_persona
        u = User.objects.create_user(username='mr', email='mario@vecchia.it', password='x')
        rossi.portal_user = u
        rossi.has_portal_access = True
        rossi.save()
        anonimizza_persona('mario@vecchia.it')
        rossi.refresh_from_db()
        assert rossi.portal_user is None and rossi.has_portal_access is False
```

- [ ] **Step 2: Verificare che falliscano**

Run: `pytest tests/test_rubrica_trasferimento.py -v`
Expected: FAIL `ImportError: cannot import name 'trasferisci_contatto'`

- [ ] **Step 3: Implementare (in coda a `sponsors/rubrica.py`)**

Aggiungere agli import in cima:

```python
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
```

```python
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
    SuppressedEmail.add(email, SuppressedEmail.Reason.ANONYMIZED)
    schede = list(Contact.all_objects.filter(email__iexact=(email or '').strip()))
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
```

Nota per l'implementatore: `Contact.save()` con `first_name='Anonimizzato'` e `last_name=''` ricompone `full_name='Anonimizzato'` (vedi `sponsors/models.py`, metodo `save`). Verificare con `grep -n "entity_type=" shared/audit_signals.py` che l'entity_type usato per i contatti sia proprio `'Contact'`; se diverso, adeguare il filtro.

- [ ] **Step 4: Test verdi**

Run: `pytest tests/test_rubrica_trasferimento.py tests/test_rubrica_destinatari.py -v`
Expected: tutti passed

- [ ] **Step 5: Commit**

```bash
git add sponsors/rubrica.py tests/test_rubrica_trasferimento.py
git diff --cached --stat
git commit -F ~/msg_rubrica.txt   # "Rubrica: trasferimento contatto ad altra azienda e anonimizzazione GDPR"
```

---

### Task 4: Import da Excel/CSV — analisi e applicazione

**Files:**
- Create: `sponsors/rubrica_import.py`
- Test: `tests/test_rubrica_import.py`

**Interfaces:**
- Produces: `leggi_file(uploaded_file) -> list[dict]` (chiavi = intestazioni minuscole); `analizza(righe: list[dict]) -> list[RigaImport]`; `applica(righe: list[dict]) -> dict` con chiavi `creati, aggiornati, aziende_create, scartati`; `RigaImport` dataclass con `numero, azienda, nome, cognome, email, ruolo, telefono, aree, esito ('nuovo'|'aggiorna'|'errore'), messaggi, nuova_azienda`.

- [ ] **Step 1: Test che falliscono**

```python
# tests/test_rubrica_import.py
"""Import rubrica: anteprima riga per riga, poi scrittura delle sole righe buone."""
import io
import pytest


def R(**kw):
    base = {'company': 'Alfa Srl', 'referente': 'Mario Rossi', 'email': 'mario@alfa.it',
            'ruolo': 'PM', 'tel': '333', 'interessi': 'Cardiologia', '_riga': 2}
    base.update(kw)
    return base


@pytest.fixture
def cardio(db):
    from sponsors.models import InterestArea
    return InterestArea.objects.create(name='Cardiologia')


@pytest.mark.django_db
class TestAnalizza:
    def test_nuovo_contatto_e_nuova_azienda(self, cardio):
        from sponsors.rubrica_import import analizza
        [r] = analizza([R()])
        assert r.esito == 'nuovo' and r.nuova_azienda
        assert (r.nome, r.cognome) == ('Mario', 'Rossi')

    def test_colonne_nome_cognome_vincono_su_referente(self, cardio):
        from sponsors.rubrica_import import analizza
        [r] = analizza([R(referente='Rossi Mario', nome='Mario', cognome='Rossi')])
        assert (r.nome, r.cognome) == ('Mario', 'Rossi')

    def test_contatto_esistente_si_aggiorna(self, cardio):
        from sponsors.models import Sponsor, Contact
        from sponsors.rubrica_import import analizza
        s = Sponsor.objects.create(legal_name='Alfa Srl', address_country='IT')
        Contact.objects.create(sponsor=s, full_name='Mario Rossi', email='MARIO@alfa.it')
        [r] = analizza([R()])
        assert r.esito == 'aggiorna' and not r.nuova_azienda

    def test_azienda_simile_ma_diversa_e_errore(self, cardio):
        from sponsors.models import Sponsor
        from sponsors.rubrica_import import analizza
        Sponsor.objects.create(legal_name='Alfa S.r.l.', address_country='IT')
        [r] = analizza([R(company='ALFA srl ')])
        assert r.esito == 'errore'
        assert any('Alfa S.r.l.' in m for m in r.messaggi)

    def test_area_sconosciuta_e_errore(self, cardio):
        from sponsors.rubrica_import import analizza
        [r] = analizza([R(interessi='Cardiologia; Cardiolgia')])
        assert r.esito == 'errore'
        assert any('Cardiolgia' in m for m in r.messaggi)

    def test_email_anonimizzata_mai_reinserita(self, cardio):
        from sponsors.models import SuppressedEmail
        from sponsors.rubrica_import import analizza
        SuppressedEmail.add('mario@alfa.it', SuppressedEmail.Reason.ANONYMIZED)
        assert analizza([R()])[0].esito == 'errore'

    def test_email_disiscritta_entra_con_avviso(self, cardio):
        from sponsors.models import SuppressedEmail
        from sponsors.rubrica_import import analizza
        SuppressedEmail.add('mario@alfa.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        [r] = analizza([R()])
        assert r.esito == 'nuovo'
        assert any('disiscritt' in m for m in r.messaggi)

    def test_email_mancante_o_non_valida(self, cardio):
        from sponsors.rubrica_import import analizza
        assert analizza([R(email='')])[0].esito == 'errore'
        assert analizza([R(email='non-una-email')])[0].esito == 'errore'

    def test_stessa_email_altra_persona_e_errore(self, cardio):
        from sponsors.models import Sponsor, Contact
        from sponsors.rubrica_import import analizza
        s = Sponsor.objects.create(legal_name='Beta Spa', address_country='IT')
        Contact.objects.create(sponsor=s, full_name='Anna Bianchi', email='mario@alfa.it')
        assert analizza([R()])[0].esito == 'errore'

    def test_riga_ripetuta_nel_file(self, cardio):
        from sponsors.rubrica_import import analizza
        righe = analizza([R(), R(_riga=3)])
        assert righe[0].esito == 'nuovo' and righe[1].esito == 'errore'


@pytest.mark.django_db
class TestApplica:
    def test_scrive_solo_le_righe_buone(self, cardio):
        from sponsors.models import Contact, Sponsor
        from sponsors.rubrica_import import applica
        esito = applica([R(), R(_riga=3, email='anna@alfa.it', referente='Anna Bianchi'),
                         R(_riga=4, email='', referente='Senza Email')])
        assert esito == {'creati': 2, 'aggiornati': 0, 'aziende_create': 1, 'scartati': 1}
        assert Sponsor.objects.filter(legal_name='Alfa Srl').count() == 1
        c = Contact.objects.get(email='mario@alfa.it')
        assert (c.first_name, c.last_name, c.job_title, c.phone) == ('Mario', 'Rossi', 'PM', '333')
        assert c.marketing_consent is True and c.marketing_consent_at is not None
        assert list(c.interest_areas.values_list('name', flat=True)) == ['Cardiologia']

    def test_aggiornamento_aggiunge_aree_e_non_svuota_campi(self, cardio):
        from sponsors.models import Sponsor, Contact, InterestArea
        from sponsors.rubrica_import import applica
        onco = InterestArea.objects.create(name='Oncologia')
        s = Sponsor.objects.create(legal_name='Alfa Srl', address_country='IT')
        c = Contact.objects.create(sponsor=s, full_name='Mario Rossi', email='mario@alfa.it',
                                   phone='999', job_title='Direttore')
        c.interest_areas.set([onco])
        esito = applica([R(tel='', ruolo='')])
        assert esito['aggiornati'] == 1
        c.refresh_from_db()
        assert (c.phone, c.job_title) == ('999', 'Direttore')
        assert set(c.interest_areas.values_list('name', flat=True)) == {'Cardiologia', 'Oncologia'}


@pytest.mark.django_db
class TestLeggiFile:
    def test_csv_con_punto_e_virgola_e_bom(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from sponsors.rubrica_import import leggi_file
        testo = '﻿Company;Referente;Email;Ruolo;Tel;Interessi\nAlfa Srl;Mario Rossi;mario@alfa.it;PM;333;Cardiologia\n'
        righe = leggi_file(SimpleUploadedFile('r.csv', testo.encode('utf-8')))
        assert righe[0]['company'] == 'Alfa Srl' and righe[0]['_riga'] == 2

    def test_xlsx(self):
        from openpyxl import Workbook
        from django.core.files.uploadedfile import SimpleUploadedFile
        from sponsors.rubrica_import import leggi_file
        wb = Workbook()
        wb.active.append(['company', 'referente', 'email'])
        wb.active.append(['Alfa Srl', 'Mario Rossi', 'mario@alfa.it'])
        wb.active.append([None, None, None])          # riga vuota: ignorata
        buf = io.BytesIO()
        wb.save(buf)
        righe = leggi_file(SimpleUploadedFile('r.xlsx', buf.getvalue()))
        assert len(righe) == 1 and righe[0]['email'] == 'mario@alfa.it'

    def test_colonna_obbligatoria_mancante(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from sponsors.rubrica_import import leggi_file
        with pytest.raises(ValueError, match='email'):
            leggi_file(SimpleUploadedFile('r.csv', b'company;referente\nAlfa;Mario\n'))
```

- [ ] **Step 2: Verificare che falliscano**

Run: `pytest tests/test_rubrica_import.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'sponsors.rubrica_import'`

- [ ] **Step 3: Implementare**

```python
# sponsors/rubrica_import.py
"""Import della rubrica condivisa (Excel o CSV).

Colonne: company, referente, email, ruolo, tel, interessi (separati da ;).
Opzionali nome e cognome: se presenti vincono su 'referente'.
Due passaggi: analizza() non scrive nulla e dice cosa succederebbe riga per
riga; applica() rifa' l'analisi sui dati aggiornati e scrive SOLO le righe
senza errori. Mai unire aziende o creare aree in silenzio."""
import csv
import io
import re
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

COLONNE_OBBLIGATORIE = ['company', 'email']
SUFFISSI_SOCIETARI = r'\b(s\.?r\.?l\.?s?|s\.?p\.?a\.?|s\.?n\.?c\.?|s\.?a\.?s\.?|ltd|gmbh|inc|unipersonale)\b'


@dataclass
class RigaImport:
    numero: int
    azienda: str
    nome: str
    cognome: str
    email: str
    ruolo: str
    telefono: str
    aree: list = field(default_factory=list)
    esito: str = 'nuovo'
    messaggi: list = field(default_factory=list)
    nuova_azienda: bool = False

    def errore(self, msg):
        self.esito = 'errore'
        self.messaggi.append(msg)


def leggi_file(f):
    """Ritorna le righe non vuote come dict {intestazione minuscola: testo},
    con la chiave '_riga' = numero di riga nel file (intestazione = 1)."""
    nome = (getattr(f, 'name', '') or '').lower()
    dati = f.read()
    if nome.endswith(('.xlsx', '.xlsm')):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(dati), read_only=True, data_only=True)
        tabella = [['' if v is None else str(v) for v in r]
                   for r in wb.active.iter_rows(values_only=True)]
    else:
        testo = dati.decode('utf-8-sig', errors='replace')
        primo = testo.splitlines()[0] if testo else ''
        sep = ';' if primo.count(';') >= primo.count(',') else ','
        tabella = list(csv.reader(io.StringIO(testo), delimiter=sep))
    if not tabella:
        raise ValueError("Il file è vuoto.")
    intest = [h.strip().lower() for h in tabella[0]]
    mancanti = [c for c in COLONNE_OBBLIGATORIE if c not in intest]
    if 'referente' not in intest and 'cognome' not in intest:
        mancanti.append('referente (oppure cognome)')
    if mancanti:
        raise ValueError("Colonne mancanti nell'intestazione: " + ', '.join(mancanti))
    righe = []
    for n, valori in enumerate(tabella[1:], start=2):
        if not any((v or '').strip() for v in valori):
            continue
        r = {h: (valori[i].strip() if i < len(valori) and valori[i] else '')
             for i, h in enumerate(intest) if h}
        r['_riga'] = n
        righe.append(r)
    return righe


def normalizza_azienda(nome):
    s = (nome or '').casefold()
    s = re.sub(SUFFISSI_SOCIETARI, ' ', s)
    s = re.sub(r'[^\w]+', ' ', s)
    return ' '.join(s.split())


def dividi_referente(testo):
    """'Mario Rossi' -> ('Mario', 'Rossi'): ultima parola = cognome, come
    Contact.save() quando c'e' solo il nome completo."""
    parti = (testo or '').split()
    if not parti:
        return '', ''
    return ' '.join(parti[:-1]), parti[-1]


def analizza(righe):
    from sponsors.models import Contact, InterestArea, Sponsor, SuppressedEmail

    aree_attive = {a.name.casefold(): a for a in InterestArea.objects.filter(is_active=True)}
    per_nome, per_norm = {}, {}
    for s in Sponsor.objects.all():
        for n in (s.legal_name, s.display_name):
            if n:
                per_nome.setdefault(n.strip().casefold(), s)
                per_norm.setdefault(normalizza_azienda(n), s)
    esclusi = dict(SuppressedEmail.objects.values_list('email', 'reason'))
    visti = {}
    out = []
    for r in righe:
        nome, cognome = r.get('nome', ''), r.get('cognome', '')
        if not (nome or cognome):
            nome, cognome = dividi_referente(r.get('referente', ''))
        riga = RigaImport(
            numero=r.get('_riga', 0), azienda=r.get('company', '').strip(),
            nome=nome.strip(), cognome=cognome.strip(),
            email=r.get('email', '').strip(), ruolo=r.get('ruolo', ''),
            telefono=r.get('tel', ''))
        email_l = riga.email.lower()

        if not riga.azienda:
            riga.errore("Manca l'azienda (colonna company).")
        if not riga.cognome:
            riga.errore("Manca il referente.")
        try:
            validate_email(riga.email)
        except ValidationError:
            riga.errore(f"Email mancante o non valida: «{riga.email}».")

        for nome_area in [a.strip() for a in re.split(r'[;,]', r.get('interessi', '')) if a.strip()]:
            area = aree_attive.get(nome_area.casefold())
            if area is None:
                riga.errore(f"Area di interesse sconosciuta: «{nome_area}». "
                            "Creala prima in Aree di interesse o correggi il file.")
            elif area.name not in riga.aree:
                riga.aree.append(area.name)

        motivo = esclusi.get(email_l)
        if motivo == SuppressedEmail.Reason.ANONYMIZED:
            riga.errore("Dati cancellati su richiesta dell'interessato (GDPR): non va reinserito.")
        elif motivo == SuppressedEmail.Reason.UNSUBSCRIBED:
            riga.messaggi.append("Si è disiscritto dal marketing: entra in rubrica ma non riceverà campagne.")

        sponsor = per_nome.get(riga.azienda.casefold())
        if sponsor is None and riga.azienda:
            simile = per_norm.get(normalizza_azienda(riga.azienda))
            if simile is not None:
                riga.errore(f"Esiste già un'azienda simile: «{simile.legal_name}». "
                            "Se è la stessa, scrivi nel file il nome esatto.")
            else:
                riga.nuova_azienda = True
                riga.messaggi.append(f"Nuova azienda: verrà creata «{riga.azienda}».")

        chiave = (normalizza_azienda(riga.azienda), email_l)
        if chiave in visti:
            riga.errore(f"Stessa azienda ed email già alla riga {visti[chiave]} del file.")
        else:
            visti[chiave] = riga.numero

        if riga.esito != 'errore' and sponsor is not None:
            esistente = Contact.objects.filter(sponsor=sponsor, email__iexact=riga.email).first()
            if esistente and esistente.left_company_at:
                riga.errore("Il contatto risulta uscito da questa azienda.")
            elif esistente:
                riga.esito = 'aggiorna'
        if riga.esito == 'nuovo':
            prova = Contact(sponsor=sponsor, first_name=riga.nome,
                            last_name=riga.cognome, email=riga.email)
            try:
                prova.clean()
            except ValidationError as e:
                for msgs in e.message_dict.values():
                    for m in msgs:
                        riga.errore(m)
        out.append(riga)
    return out


def applica(righe):
    from sponsors.models import Contact, InterestArea, Sponsor

    esito = {'creati': 0, 'aggiornati': 0, 'aziende_create': 0, 'scartati': 0}
    aree = {a.name: a for a in InterestArea.objects.all()}
    nuove_aziende = {}
    adesso = timezone.now()
    for r in analizza(righe):
        if r.esito == 'errore':
            esito['scartati'] += 1
            continue
        with transaction.atomic():
            if r.nuova_azienda:
                chiave = normalizza_azienda(r.azienda)
                sponsor = nuove_aziende.get(chiave)
                if sponsor is None:
                    sponsor = Sponsor.objects.create(legal_name=r.azienda, address_country='IT')
                    nuove_aziende[chiave] = sponsor
                    esito['aziende_create'] += 1
            else:
                sponsor = (Sponsor.objects.filter(legal_name__iexact=r.azienda).first()
                           or Sponsor.objects.filter(display_name__iexact=r.azienda).first())
            contatto = Contact.objects.filter(sponsor=sponsor, email__iexact=r.email).first()
            if contatto is None:
                contatto = Contact(sponsor=sponsor, email=r.email,
                                   first_name=r.nome, last_name=r.cognome)
                esito['creati'] += 1
            else:
                esito['aggiornati'] += 1
            if r.telefono:
                contatto.phone = r.telefono
            if r.ruolo:
                contatto.job_title = r.ruolo
            if not contatto.marketing_consent:
                contatto.marketing_consent = True
                contatto.marketing_consent_at = adesso
            contatto.save()
            contatto.interest_areas.add(*[aree[n] for n in r.aree])
    return esito
```

Nota: nel caso "riga ripetuta nel file" con azienda NUOVA la seconda riga e' gia' in errore da `analizza`, quindi `applica` crea l'azienda una sola volta grazie a `nuove_aziende`.

- [ ] **Step 4: Test verdi**

Run: `pytest tests/test_rubrica_import.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add sponsors/rubrica_import.py tests/test_rubrica_import.py
git diff --cached --stat
git commit -F ~/msg_rubrica.txt   # "Rubrica: import Excel/CSV con anteprima riga per riga"
```

---

### Task 5: Admin — aree, contatti, email escluse

**Files:**
- Modify: `sponsors/admin.py` (import modelli in cima; ContactAdmin righe ~718-800; nuove classi in coda)
- Test: `tests/test_rubrica_admin.py`

**Interfaces:**
- Consumes: modelli Task 1.
- Produces: admin registrati per `InterestArea`, `SuppressedEmail`; su ContactAdmin il fieldset "Rubrica", filtri, colonna "Uscito". URL names usati dai task successivi: `admin:sponsors_contact_importa_rubrica`, `admin:sponsors_contact_trasferisci`, `admin:sponsors_contact_anonimizza`.

- [ ] **Step 1: Test che falliscono**

```python
# tests/test_rubrica_admin.py
"""Pagine admin della rubrica (si aprono, mostrano i campi nuovi)."""
import pytest
from django.urls import reverse


@pytest.fixture
def staff_client(client, db):
    from users.models import User
    u = User.objects.create_superuser(username='staff', email='staff@test.it', password='x')
    client.force_login(u)
    return client


@pytest.mark.django_db
class TestAdminRubrica:
    def test_lista_aree(self, staff_client):
        from sponsors.models import InterestArea
        InterestArea.objects.create(name='Cardiologia')
        resp = staff_client.get(reverse('admin:sponsors_interestarea_changelist'))
        assert resp.status_code == 200 and b'Cardiologia' in resp.content

    def test_scheda_contatto_ha_aree_e_uscita(self, staff_client, contact):
        resp = staff_client.get(reverse('admin:sponsors_contact_change', args=[contact.pk]))
        assert resp.status_code == 200
        assert b'interest_areas' in resp.content
        assert b'Non pi' in resp.content            # "Non più in azienda dal"

    def test_filtro_lista_contatti_per_area(self, staff_client, contact):
        from sponsors.models import InterestArea
        a = InterestArea.objects.create(name='Cardiologia')
        contact.interest_areas.set([a])
        resp = staff_client.get(reverse('admin:sponsors_contact_changelist')
                                + f'?interest_areas__id__exact={a.pk}')
        assert resp.status_code == 200 and contact.email.encode() in resp.content

    def test_lista_email_escluse(self, staff_client):
        from sponsors.models import SuppressedEmail
        SuppressedEmail.add('via@x.it', SuppressedEmail.Reason.UNSUBSCRIBED)
        resp = staff_client.get(reverse('admin:sponsors_suppressedemail_changelist'))
        assert resp.status_code == 200 and b'via@x.it' in resp.content
```

- [ ] **Step 2: Verificare che falliscano**

Run: `pytest tests/test_rubrica_admin.py -v`
Expected: FAIL `NoReverseMatch` per `sponsors_interestarea_changelist`

- [ ] **Step 3: Implementare**

Nell'import dei modelli in cima a `sponsors/admin.py` aggiungere `InterestArea, SuppressedEmail, InterestCampaign` (verificare la riga con `grep -n "from .models import\|from sponsors.models import" sponsors/admin.py`).

In `ContactAdmin`:
- `list_display`: aggiungere `'col_uscito'` in fondo.
- `list_filter`: aggiungere `'interest_areas', ('left_company_at', admin.EmptyFieldListFilter)`.
- `filter_horizontal = ('interest_areas',)`
- nel `fieldsets`, subito dopo il blocco `('Funzioni', {...})`:

```python
        ('Rubrica', {
            'fields': ('interest_areas', 'left_company_at', 'azioni_rubrica'),
            'description': "Aree di interesse della persona. «Non più in azienda dal» "
                           "si compila con il pulsante Trasferisci, non a mano.",
        }),
```

- `readonly_fields`: aggiungere `'left_company_at', 'azioni_rubrica'`.
- metodi (dentro ContactAdmin):

```python
    @admin.display(description='Uscito', ordering='left_company_at')
    def col_uscito(self, obj):
        return f"dal {obj.left_company_at:%d/%m/%Y}" if obj.left_company_at else ''

    @admin.display(description='Azioni')
    def azioni_rubrica(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        if not obj or not obj.pk:
            return '—'
        links = []
        if not obj.left_company_at:
            links.append(format_html('<a class="button" href="{}">Trasferisci in altra azienda</a>',
                                     reverse('admin:sponsors_contact_trasferisci', args=[obj.pk])))
        links.append(format_html('<a class="button" style="background:#b91c1c" href="{}">'
                                 'Cancella dati (GDPR)</a>',
                                 reverse('admin:sponsors_contact_anonimizza', args=[obj.pk])))
        return format_html(' '.join(['{}'] * len(links)), *links)
```

Questi link puntano a URL dei Task 6-7: per far passare i test di questo task registrare SUBITO in `ContactAdmin.get_urls` le tre rotte con viste provvisorie che rispondono `HttpResponseRedirect` alla changelist; i Task 6 e 7 le sostituiscono. Codice:

```python
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path('importa-rubrica/', self.admin_site.admin_view(self.importa_rubrica_view),
                 name='sponsors_contact_importa_rubrica'),
            path('<path:object_id>/trasferisci/', self.admin_site.admin_view(self.trasferisci_view),
                 name='sponsors_contact_trasferisci'),
            path('<path:object_id>/anonimizza/', self.admin_site.admin_view(self.anonimizza_view),
                 name='sponsors_contact_anonimizza'),
        ]
        return custom + urls

    def importa_rubrica_view(self, request):
        from django.shortcuts import redirect
        return redirect('admin:sponsors_contact_changelist')

    def trasferisci_view(self, request, object_id):
        from django.shortcuts import redirect
        return redirect('admin:sponsors_contact_changelist')

    def anonimizza_view(self, request, object_id):
        from django.shortcuts import redirect
        return redirect('admin:sponsors_contact_changelist')
```

Prima di aggiungere `get_urls` controllare con `grep -n "def get_urls" sponsors/admin.py` che ContactAdmin (riga ~718) non ne abbia gia' uno; se c'e', fondere le rotte.

In coda al file:

```python
@admin.register(InterestArea)
class InterestAreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'n_contatti')
    list_filter = ('is_active',)
    search_fields = ('name',)

    def get_queryset(self, request):
        from django.db.models import Count, Q
        return super().get_queryset(request).annotate(
            _n=Count('contacts', filter=Q(contacts__deleted_at__isnull=True,
                                          contacts__left_company_at__isnull=True)))

    @admin.display(description='Contatti', ordering='_n')
    def n_contatti(self, obj):
        return obj._n


@admin.register(SuppressedEmail)
class SuppressedEmailAdmin(admin.ModelAdmin):
    """Le esclusioni nascono dal link di disiscrizione o dall'anonimizzazione.
    Togliere una DISISCRIZIONE riammette l'indirizzo alle campagne (solo se la
    persona lo chiede); le anonimizzazioni non si toccano."""
    list_display = ('email', 'reason', 'created_at')
    list_filter = ('reason',)
    search_fields = ('email',)
    readonly_fields = ('email', 'reason', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return obj is None or obj.reason == SuppressedEmail.Reason.UNSUBSCRIBED
```

Nella scheda azienda (SponsorAdmin, riga ~201) aggiungere un campo di sola lettura con l'unione delle aree dei contatti attivi:

```python
    @admin.display(description='Aree di interesse (dai contatti)')
    def aree_azienda(self, obj):
        if not obj or not obj.pk:
            return '—'
        from sponsors.models import InterestArea
        nomi = (InterestArea.objects
                .filter(contacts__sponsor=obj, contacts__deleted_at__isnull=True,
                        contacts__left_company_at__isnull=True)
                .distinct().values_list('name', flat=True))
        return ', '.join(nomi) or '—'
```

e aggiungerlo a `readonly_fields` e al primo fieldset di SponsorAdmin (leggere prima il fieldset con `grep -n "fieldsets" -A6 sponsors/admin.py | head -20`).

- [ ] **Step 4: Test verdi e check**

Run: `python manage.py check && pytest tests/test_rubrica_admin.py -v`
Expected: no issues; 4 passed

- [ ] **Step 5: Commit**

```bash
git add sponsors/admin.py tests/test_rubrica_admin.py
git diff --cached --stat
git commit -F ~/msg_rubrica.txt   # "Rubrica: admin aree di interesse, email escluse e campi rubrica sui contatti"
```

---

### Task 6: Pagina di import con anteprima

**Files:**
- Modify: `sponsors/admin.py` (`ContactAdmin.importa_rubrica_view`, `change_list_template`)
- Create: `sponsors/templates/admin/sponsors/contact/importa_rubrica.html`
- Create: `sponsors/templates/admin/sponsors/contact/change_list.html`
- Test: `tests/test_rubrica_admin.py` (aggiunte)

**Interfaces:**
- Consumes: `leggi_file`, `analizza`, `applica` (Task 4).

- [ ] **Step 1: Test che falliscono (aggiungere a `tests/test_rubrica_admin.py`)**

```python
@pytest.mark.django_db
class TestImportAdmin:
    URL = 'admin:sponsors_contact_importa_rubrica'

    def _csv(self, testo):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile('r.csv', testo.encode('utf-8'))

    def test_pulsante_in_lista_contatti(self, staff_client):
        resp = staff_client.get(reverse('admin:sponsors_contact_changelist'))
        assert reverse(self.URL).encode() in resp.content

    def test_anteprima_non_scrive_nulla(self, staff_client):
        from sponsors.models import Contact
        resp = staff_client.post(reverse(self.URL), {'file': self._csv(
            'company;referente;email\nAlfa Srl;Mario Rossi;mario@alfa.it\n')})
        assert resp.status_code == 200
        assert b'mario@alfa.it' in resp.content and b'Nuova azienda' in resp.content
        assert not Contact.objects.filter(email='mario@alfa.it').exists()

    def test_conferma_scrive(self, staff_client):
        from sponsors.models import Contact
        resp = staff_client.post(reverse(self.URL), {'file': self._csv(
            'company;referente;email\nAlfa Srl;Mario Rossi;mario@alfa.it\n')})
        dati = resp.context['dati']
        resp = staff_client.post(reverse(self.URL), {'conferma': '1', 'dati': dati})
        assert resp.status_code == 302
        assert Contact.objects.filter(email='mario@alfa.it').exists()

    def test_dati_manomessi_rifiutati(self, staff_client):
        from sponsors.models import Contact
        resp = staff_client.post(reverse(self.URL), {'conferma': '1', 'dati': 'falso'})
        assert resp.status_code == 302
        assert Contact.objects.count() == 0

    def test_file_senza_colonne_mostra_errore(self, staff_client):
        resp = staff_client.post(reverse(self.URL), {'file': self._csv('a;b\n1;2\n')})
        assert resp.status_code == 200 and b'Colonne mancanti' in resp.content
```

- [ ] **Step 2: Verificare che falliscano**

Run: `pytest tests/test_rubrica_admin.py::TestImportAdmin -v`
Expected: FAIL (la vista provvisoria fa redirect, niente pulsante)

- [ ] **Step 3: Implementare la vista**

Sostituire `importa_rubrica_view` in ContactAdmin:

```python
    def importa_rubrica_view(self, request):
        """GET: form di caricamento. POST con file: anteprima (non scrive).
        POST con conferma: riapplica l'analisi e scrive le righe buone.
        Le righe passano dall'anteprima alla conferma firmate (signing), cosi'
        non servono file temporanei e non si possono alterare."""
        import logging
        from django.contrib import messages
        from django.core import signing
        from django.shortcuts import redirect
        from django.template.response import TemplateResponse
        from sponsors.rubrica_import import analizza, applica, leggi_file

        logger = logging.getLogger(__name__)
        SALT = 'rubrica-import'
        ctx = {**self.admin_site.each_context(request), 'opts': self.model._meta,
               'title': 'Importa rubrica'}

        if request.method == 'POST' and request.POST.get('conferma'):
            try:
                righe = signing.loads(request.POST.get('dati', ''), salt=SALT, max_age=3600)
            except signing.BadSignature:
                self.message_user(request, "Anteprima scaduta o non valida: ricarica il file.",
                                  level=messages.ERROR)
                return redirect('admin:sponsors_contact_importa_rubrica')
            try:
                esito = applica(righe)
            except Exception as e:
                logger.exception("Import rubrica fallito")
                self.message_user(request, f"Import non riuscito ({type(e).__name__}): {e}",
                                  level=messages.ERROR)
                return redirect('admin:sponsors_contact_importa_rubrica')
            self.message_user(request, (
                f"Import completato: {esito['creati']} contatti creati, "
                f"{esito['aggiornati']} aggiornati, {esito['aziende_create']} aziende nuove, "
                f"{esito['scartati']} righe scartate."))
            return redirect('admin:sponsors_contact_changelist')

        if request.method == 'POST' and request.FILES.get('file'):
            try:
                righe = leggi_file(request.FILES['file'])
            except ValueError as e:
                ctx['errore'] = str(e)
                return TemplateResponse(request, 'admin/sponsors/contact/importa_rubrica.html', ctx)
            except Exception as e:
                logger.exception("Lettura file rubrica fallita")
                ctx['errore'] = f"Impossibile leggere il file ({type(e).__name__}). Usa .xlsx o .csv."
                return TemplateResponse(request, 'admin/sponsors/contact/importa_rubrica.html', ctx)
            analisi = analizza(righe)
            ctx.update({
                'analisi': analisi,
                'dati': signing.dumps(righe, salt=SALT, compress=True),
                'n_nuovi': sum(r.esito == 'nuovo' for r in analisi),
                'n_aggiorna': sum(r.esito == 'aggiorna' for r in analisi),
                'n_errori': sum(r.esito == 'errore' for r in analisi),
            })
        return TemplateResponse(request, 'admin/sponsors/contact/importa_rubrica.html', ctx)
```

- [ ] **Step 4: Template anteprima**

```html
{# sponsors/templates/admin/sponsors/contact/importa_rubrica.html #}
{% extends "admin/base_site.html" %}
{% block content %}
<div style="max-width:1100px">
  <p>Carica un file <strong>.xlsx</strong> o <strong>.csv</strong> con le colonne
     <code>company</code>, <code>referente</code>, <code>email</code>, <code>ruolo</code>,
     <code>tel</code>, <code>interessi</code> (aree separate da <code>;</code>).
     Prima vedi l'anteprima: nulla viene salvato finché non confermi.</p>

  {% if errore %}<p class="errornote">{{ errore }}</p>{% endif %}

  <form method="post" enctype="multipart/form-data">{% csrf_token %}
    <input type="file" name="file" accept=".xlsx,.csv" required>
    <input type="submit" value="Mostra anteprima">
  </form>

  {% if analisi %}
  <h2 style="margin-top:24px">Anteprima</h2>
  <p><strong>{{ n_nuovi }}</strong> nuovi · <strong>{{ n_aggiorna }}</strong> da aggiornare ·
     <strong style="color:#b91c1c">{{ n_errori }}</strong> con errori (non verranno importati)</p>
  <table style="width:100%">
    <thead><tr><th>Riga</th><th>Esito</th><th>Azienda</th><th>Nome</th><th>Cognome</th>
      <th>Email</th><th>Aree</th><th>Note</th></tr></thead>
    <tbody>
    {% for r in analisi %}
      <tr style="{% if r.esito == 'errore' %}background:rgba(185,28,28,.08){% endif %}">
        <td>{{ r.numero }}</td>
        <td>{% if r.esito == 'nuovo' %}Nuovo{% elif r.esito == 'aggiorna' %}Aggiorna{% else %}<strong style="color:#b91c1c">Errore</strong>{% endif %}</td>
        <td>{{ r.azienda }}</td><td>{{ r.nome }}</td><td>{{ r.cognome }}</td>
        <td>{{ r.email }}</td><td>{{ r.aree|join:", " }}</td>
        <td>{{ r.messaggi|join:" " }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  {% if n_nuovi or n_aggiorna %}
  <form method="post" style="margin-top:16px">{% csrf_token %}
    <input type="hidden" name="dati" value="{{ dati }}">
    <input type="hidden" name="conferma" value="1">
    <input type="submit" class="default" value="Importa {{ n_nuovi|add:n_aggiorna }} righe">
  </form>
  {% endif %}
  {% endif %}
</div>
{% endblock %}
```

Attenzione: la riga di commento `{# ... #}` in cima e' su una riga sola. Pulsante in lista contatti:

```html
{# sponsors/templates/admin/sponsors/contact/change_list.html #}
{% extends "admin/anagrafica_change_list.html" %}
{% block object-tools-items %}
  {{ block.super }}
  <li><a href="{% url 'admin:sponsors_contact_importa_rubrica' %}">Importa rubrica</a></li>
{% endblock %}
```

In ContactAdmin cambiare `change_list_template = 'admin/sponsors/contact/change_list.html'` (SponsorAdmin continua a usare `admin/anagrafica_change_list.html`).

- [ ] **Step 5: Test verdi + controllo commenti template**

Run: `pytest tests/test_rubrica_admin.py -v && grep -rn '{#' sponsors/templates/admin/sponsors/contact/ | grep -v '#}'`
Expected: tutti passed; il grep non stampa nulla

- [ ] **Step 6: Commit**

```bash
git add sponsors/admin.py sponsors/templates/admin/sponsors/contact/importa_rubrica.html sponsors/templates/admin/sponsors/contact/change_list.html tests/test_rubrica_admin.py
git diff --cached --stat
git commit -F ~/msg_rubrica.txt   # "Rubrica: pagina di import con anteprima dalla lista contatti"
```

---

### Task 7: Pagine Trasferisci e Cancella dati (GDPR)

**Files:**
- Modify: `sponsors/admin.py` (`trasferisci_view`, `anonimizza_view`)
- Create: `sponsors/templates/admin/sponsors/contact/trasferisci.html`, `sponsors/templates/admin/sponsors/contact/anonimizza.html`
- Test: `tests/test_rubrica_admin.py` (aggiunte)

**Interfaces:**
- Consumes: `trasferisci_contatto`, `anonimizza_persona` (Task 3).

- [ ] **Step 1: Test che falliscono**

```python
@pytest.mark.django_db
class TestTrasferisciAnonimizzaAdmin:
    def test_trasferisci(self, staff_client, contact):
        from sponsors.models import Sponsor, Contact
        nuova = Sponsor.objects.create(legal_name='Nuova Spa', address_country='IT')
        url = reverse('admin:sponsors_contact_trasferisci', args=[contact.pk])
        assert staff_client.get(url).status_code == 200
        resp = staff_client.post(url, {'nuova_azienda': nuova.pk, 'nuova_email': '',
                                       'data': '2026-10-01'})
        nuovo = Contact.objects.get(sponsor=nuova)
        assert resp.status_code == 302
        assert resp['Location'] == reverse('admin:sponsors_contact_change', args=[nuovo.pk])
        contact.refresh_from_db()
        assert str(contact.left_company_at) == '2026-10-01'

    def test_anonimizza_chiede_conferma_poi_esegue(self, staff_client, contact):
        from sponsors.models import Contact
        url = reverse('admin:sponsors_contact_anonimizza', args=[contact.pk])
        resp = staff_client.get(url)
        assert resp.status_code == 200 and contact.email.encode() in resp.content
        resp = staff_client.post(url, {'conferma': '1'})
        assert resp.status_code == 302
        assert Contact.all_objects.get(pk=contact.pk).full_name == 'Anonimizzato'

    def test_anonimizza_negato_a_operatore(self, client, contact):
        from users.models import User
        op = User.objects.create_user(username='op', email='op@test.it', password='x',
                                      is_staff=True, role='operator')
        from django.contrib.auth.models import Permission
        op.user_permissions.add(*Permission.objects.filter(codename__in=['view_contact', 'change_contact']))
        client.force_login(op)
        resp = client.post(reverse('admin:sponsors_contact_anonimizza', args=[contact.pk]),
                           {'conferma': '1'})
        assert resp.status_code == 403
```

- [ ] **Step 2: Verificare che falliscano**

Run: `pytest tests/test_rubrica_admin.py::TestTrasferisciAnonimizzaAdmin -v`
Expected: FAIL (viste provvisorie)

- [ ] **Step 3: Implementare**

Sostituire le due viste provvisorie in ContactAdmin:

```python
    def trasferisci_view(self, request, object_id):
        from django import forms
        from django.core.exceptions import PermissionDenied, ValidationError
        from django.shortcuts import get_object_or_404, redirect
        from django.template.response import TemplateResponse
        from django.utils import timezone
        from sponsors.models import Sponsor
        from sponsors.rubrica import trasferisci_contatto

        contatto = get_object_or_404(Contact, pk=object_id)
        if not self.has_change_permission(request, contatto):
            raise PermissionDenied

        class TrasferisciForm(forms.Form):
            nuova_azienda = forms.ModelChoiceField(
                queryset=Sponsor.objects.exclude(pk=contatto.sponsor_id).order_by('legal_name'),
                label='Nuova azienda')
            nuova_email = forms.EmailField(
                required=False, label='Nuova email',
                help_text='Lascia vuoto se resta la stessa.')
            data = forms.DateField(
                label='In azienda nuova dal', initial=timezone.localdate,
                widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))

        form = TrasferisciForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            try:
                nuovo = trasferisci_contatto(contatto, form.cleaned_data['nuova_azienda'],
                                             form.cleaned_data['nuova_email'],
                                             form.cleaned_data['data'])
            except ValidationError as e:
                form.add_error(None, e)
            else:
                self.message_user(request, (
                    f"{nuovo.full_name} ora è in {nuovo.sponsor.legal_name}. "
                    f"La scheda in {contatto.sponsor.legal_name} resta per lo storico. "
                    "Se serve l'accesso al portale, invitalo di nuovo."))
                return redirect('admin:sponsors_contact_change', nuovo.pk)
        return TemplateResponse(request, 'admin/sponsors/contact/trasferisci.html', {
            **self.admin_site.each_context(request), 'opts': self.model._meta,
            'title': f'Trasferisci {contatto.full_name}', 'contatto': contatto, 'form': form})

    def anonimizza_view(self, request, object_id):
        from django.core.exceptions import PermissionDenied
        from django.shortcuts import get_object_or_404, redirect
        from django.template.response import TemplateResponse
        from sponsors.rubrica import anonimizza_persona

        if not (request.user.is_superuser or getattr(request.user, 'role', '') == 'admin'):
            raise PermissionDenied
        contatto = get_object_or_404(Contact.all_objects, pk=object_id)
        schede = (Contact.all_objects.filter(email__iexact=contatto.email)
                  .select_related('sponsor'))
        if request.method == 'POST' and request.POST.get('conferma'):
            n = anonimizza_persona(contatto.email)
            self.message_user(request, f"Dati cancellati: {n} schede anonimizzate. "
                                       "L'indirizzo non potrà più essere reimportato.")
            return redirect('admin:sponsors_contact_changelist')
        return TemplateResponse(request, 'admin/sponsors/contact/anonimizza.html', {
            **self.admin_site.each_context(request), 'opts': self.model._meta,
            'title': 'Cancella dati personali (GDPR)', 'contatto': contatto, 'schede': schede})
```

Template:

```html
{# sponsors/templates/admin/sponsors/contact/trasferisci.html #}
{% extends "admin/base_site.html" %}
{% block content %}
<p>{{ contatto.full_name }} lascia <strong>{{ contatto.sponsor.legal_name }}</strong>.
   Viene creata una nuova scheda nella nuova azienda (con telefono, lingua e aree di interesse);
   quella attuale resta per i contratti già firmati ma non riceverà più comunicazioni.</p>
<form method="post">{% csrf_token %}
  {{ form.as_p }}
  <input type="submit" class="default" value="Trasferisci">
  <a href="{% url 'admin:sponsors_contact_change' contatto.pk %}">Annulla</a>
</form>
{% endblock %}
```

```html
{# sponsors/templates/admin/sponsors/contact/anonimizza.html #}
{% extends "admin/base_site.html" %}
{% block content %}
<p class="errornote">Operazione <strong>irreversibile</strong>: da usare solo se la persona ha
   chiesto la cancellazione dei propri dati.</p>
<p>Verranno anonimizzate tutte le schede con l'email <strong>{{ contatto.email }}</strong>:</p>
<ul>{% for s in schede %}<li>{{ s.full_name }} — {{ s.sponsor.legal_name }}</li>{% endfor %}</ul>
<p>Nome, email, telefono e dati anagrafici vengono sostituiti; le schede restano (cestinate) per
   non rompere i contratti. L'indirizzo finisce tra le email escluse e non potrà essere reimportato.</p>
<form method="post">{% csrf_token %}
  <input type="hidden" name="conferma" value="1">
  <input type="submit" value="Cancella i dati" style="background:#b91c1c;color:#fff">
  <a href="{% url 'admin:sponsors_contact_change' contatto.pk %}">Annulla</a>
</form>
{% endblock %}
```

- [ ] **Step 4: Test verdi**

Run: `pytest tests/test_rubrica_admin.py -v && grep -rn '{#' sponsors/templates/admin/sponsors/contact/ | grep -v '#}'`
Expected: tutti passed; grep vuoto

- [ ] **Step 5: Commit**

```bash
git add sponsors/admin.py sponsors/templates/admin/sponsors/contact/trasferisci.html sponsors/templates/admin/sponsors/contact/anonimizza.html tests/test_rubrica_admin.py
git diff --cached --stat
git commit -F ~/msg_rubrica.txt   # "Rubrica: trasferimento ad altra azienda e cancellazione dati GDPR dalla scheda contatto"
```

---

### Task 8: Campagne per aree di interesse + disiscrizione globale

**Files:**
- Modify: `contracts/tasks/notifications.py` (in coda), `portal/views/campaigns.py`, `portal/urls.py:48`, `portal/templates/portal/campaign_unsubscribe.html`, `sponsors/admin.py` (InterestCampaignAdmin)
- Test: `tests/test_rubrica_campagne.py`

**Interfaces:**
- Consumes: `destinatari_per_aree` (Task 2), `SuppressedEmail.add` (Task 1).
- Produces: task `send_interest_campaign(campaign_id, test_to=None) -> int`; URL `portal:marketing_unsubscribe` con token `signing.dumps({'e': email_minuscola}, salt='marketing-optout')`.

- [ ] **Step 1: Test che falliscono**

```python
# tests/test_rubrica_campagne.py
"""Campagne per aree di interesse: invio, prova, disiscrizione globale."""
import re
import pytest
from django.core import mail, signing
from django.urls import reverse


@pytest.fixture
def campagna(db):
    from sponsors.models import InterestArea, InterestCampaign, Sponsor, Contact
    a = InterestArea.objects.create(name='Cardiologia')
    s = Sponsor.objects.create(legal_name='Alfa Srl', address_country='IT')
    for nome, email in (('Mario Rossi', 'mario@alfa.it'), ('Anna Bianchi', 'anna@alfa.it')):
        Contact.objects.create(sponsor=s, full_name=nome, email=email).interest_areas.set([a])
    c = InterestCampaign.objects.create(
        name='Congresso cardio', subject={'it': 'Novità per {{ sponsor.legal_name }}'},
        body={'it': '<p>Gentile {{ contact.full_name }}, ecco il congresso.</p>'})
    c.interest_areas.set([a])
    return c


@pytest.mark.django_db
class TestInvio:
    def test_invia_a_tutti_i_destinatari_personalizzata(self, campagna):
        from contracts.tasks.notifications import send_interest_campaign
        assert send_interest_campaign(campagna.pk) == 2
        assert sorted(m.to[0] for m in mail.outbox) == ['anna@alfa.it', 'mario@alfa.it']
        m = next(m for m in mail.outbox if m.to == ['mario@alfa.it'])
        assert m.subject == 'Novità per Alfa Srl'
        html = m.alternatives[0][0] if m.alternatives else m.body
        assert 'Mario Rossi' in html and '/campagne/disiscrizione/' in html
        campagna.refresh_from_db()
        assert campagna.sent_count == 2

    def test_prova_va_solo_al_tester(self, campagna):
        from contracts.tasks.notifications import send_interest_campaign
        assert send_interest_campaign(campagna.pk, test_to='io@valet.it') == 1
        assert [m.to for m in mail.outbox] == [['io@valet.it']]
        assert mail.outbox[0].subject.startswith('[PROVA]')
        campagna.refresh_from_db()
        assert campagna.sent_count == 0


@pytest.mark.django_db
class TestDisiscrizioneGlobale:
    def test_link_disiscrive_da_tutto_il_marketing(self, client, campagna):
        from sponsors.models import SuppressedEmail
        token = signing.dumps({'e': 'mario@alfa.it'}, salt='marketing-optout')
        resp = client.get(reverse('portal:marketing_unsubscribe', args=[token]))
        assert resp.status_code == 200
        assert SuppressedEmail.is_suppressed('mario@alfa.it')
        from contracts.tasks.notifications import send_interest_campaign
        assert send_interest_campaign(campagna.pk) == 1

    def test_token_manomesso(self, client):
        from sponsors.models import SuppressedEmail
        resp = client.get(reverse('portal:marketing_unsubscribe', args=['falso']))
        assert resp.status_code == 200 and SuppressedEmail.objects.count() == 0


@pytest.mark.django_db
class TestAdminInvio:
    def test_invio_una_sola_volta(self, client, campagna):
        from users.models import User
        u = User.objects.create_superuser(username='s', email='s@valet.it', password='x')
        client.force_login(u)
        url = reverse('admin:sponsors_interestcampaign_changelist')
        dati = {'action': 'action_invia', '_selected_action': [campagna.pk]}
        client.post(url, dati)
        client.post(url, dati)                          # doppio clic
        assert len(mail.outbox) == 2                    # 2 destinatari, una volta sola
        campagna.refresh_from_db()
        assert campagna.sent_at is not None and campagna.sent_by == u
```

- [ ] **Step 2: Verificare che falliscano**

Run: `pytest tests/test_rubrica_campagne.py -v`
Expected: FAIL `ImportError: cannot import name 'send_interest_campaign'`

- [ ] **Step 3: Task di invio (in coda a `contracts/tasks/notifications.py`)**

```python
# ============================================================================
# Campagne per aree di interesse (rubrica)
# ============================================================================

MARKETING_UNSUB_SALT = 'marketing-optout'

_MARKETING_UNSUB_TEXT = {
    'it': {
        'intro': ("Non vuoi più ricevere le nostre comunicazioni promozionali? "
                 "Le email relative ai tuoi contratti continueranno ad arrivarti."),
        'label': 'Disiscriviti dalle comunicazioni promozionali',
    },
    'en': {
        'intro': ("Don't want to receive our promotional emails anymore? "
                 "Emails about your contracts will keep arriving as usual."),
        'label': 'Unsubscribe from promotional emails',
    },
}


@shared_task(bind=True, max_retries=0)
def send_interest_campaign(self, campaign_id, test_to=None):
    """Invia una campagna per aree di interesse: una email per indirizzo
    (vedi destinatari_per_aree). Con test_to manda UNA sola email di prova a
    quell'indirizzo, personalizzata col primo destinatario, senza contarla.
    Un errore su un destinatario non blocca gli altri."""
    from django.conf import settings
    from django.core import signing
    from django.template import engines
    from django.urls import reverse
    from contracts.services.email_sender import send_email, _pick_lang
    from sponsors.models import InterestCampaign
    from sponsors.rubrica import destinatari_per_aree

    try:
        campaign = InterestCampaign.objects.get(pk=campaign_id)
    except InterestCampaign.DoesNotExist:
        logger.error("Campagna per aree %s non trovata", campaign_id)
        return 0

    destinatari = destinatari_per_aree(campaign.interest_areas.all())
    if test_to:
        destinatari = destinatari[:1]
    base_url = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    dj = engines['django']

    sent = 0
    for contact in destinatari:
        lang = contact.preferred_language if contact.preferred_language in ('it', 'en') else 'it'
        placeholders = {'sponsor': contact.sponsor, 'contact': contact, 'event_name': ''}
        body = _pick_lang(campaign.body, lang) or ''
        if not body.strip():
            continue
        subject = dj.from_string(_pick_lang(campaign.subject, lang) or campaign.name).render(placeholders)
        token = signing.dumps({'e': contact.email.strip().lower()}, salt=MARKETING_UNSUB_SALT)
        txt = _MARKETING_UNSUB_TEXT.get(lang, _MARKETING_UNSUB_TEXT['it'])
        try:
            send_email(
                template_name='promotional_campaign',
                context={
                    **placeholders,
                    'unsubscribe_url': base_url + reverse('portal:marketing_unsubscribe', args=[token]),
                    'unsubscribe_intro': txt['intro'],
                    'unsubscribe_label': txt['label'],
                },
                to=[test_to or contact.email],
                subject=('[PROVA] ' if test_to else '') + subject,
                language=lang,
                custom_body_html=body,
                related_to=campaign,
                communication_type='promotional_campaign',
                is_automated=not test_to,
            )
            sent += 1
        except Exception:
            logger.exception("Invio campagna per aree %s a %s fallito", campaign_id, contact.email)

    if not test_to:
        InterestCampaign.objects.filter(pk=campaign.pk).update(sent_count=sent)
    logger.info("Campagna per aree '%s': %d email%s", campaign.name, sent,
                ' (prova)' if test_to else '')
    return sent
```

- [ ] **Step 4: Vista e URL di disiscrizione globale**

In `portal/views/campaigns.py`, in coda:

```python
MARKETING_UNSUB_SALT = 'marketing-optout'


@require_GET
def marketing_unsubscribe_view(request, token):
    """Disiscrive l'INDIRIZZO da tutte le campagne promozionali (per area e
    per evento). Idempotente. Le email transazionali continuano."""
    from sponsors.models import SuppressedEmail

    esito = 'errore'
    try:
        data = signing.loads(token, salt=MARKETING_UNSUB_SALT)
        if SuppressedEmail.add(data.get('e'), SuppressedEmail.Reason.UNSUBSCRIBED):
            esito = 'ok'
            logger.info("Disiscrizione marketing globale registrata")
    except signing.BadSignature:
        esito = 'errore'
    except Exception:
        logger.exception("Errore disiscrizione marketing (token=%s)", token)
    return render(request, 'portal/campaign_unsubscribe.html', {
        'esito': esito, 'campaign': None, 'globale': True})
```

In `portal/urls.py`, dopo la rotta `campaign_unsubscribe` (riga 48-49):

```python
    path('campagne/disiscrizione/<str:token>/', portal_campaigns.marketing_unsubscribe_view,
         name='marketing_unsubscribe'),
```

In `portal/templates/portal/campaign_unsubscribe.html` sostituire il blocco `{% if campaign %}...{% else %}...{% endif %}` del caso ok con:

```html
      {% if globale %}
        {% trans "Non riceverai più le nostre comunicazioni promozionali." %}
      {% elif campaign %}
        {% blocktrans with ev=campaign.event %}Non riceverai più questo tipo di comunicazioni per <strong>{{ ev }}</strong>.{% endblocktrans %}
      {% else %}
        {% trans "Non riceverai più questo tipo di comunicazioni." %}
      {% endif %}
```

Poi aggiornare le traduzioni: `python manage.py makemessages -l en` e tradurre in `locale/en/LC_MESSAGES/django.po` la nuova stringa con "You will no longer receive our promotional emails."; compilare con `msgfmt --check -o locale/en/LC_MESSAGES/django.mo locale/en/LC_MESSAGES/django.po` (exit code 0).

- [ ] **Step 5: Admin campagne (in coda a `sponsors/admin.py`)**

```python
class InterestCampaignForm(forms.ModelForm):
    subject = TranslatableJSONField(languages=['it', 'en'], required_languages=['it'], label='Oggetto')
    body = TranslatableJSONField(
        languages=['it', 'en'], required_languages=['it'], wysiwyg=True, label='Corpo email',
        help_text="Il link di disiscrizione viene aggiunto automaticamente in fondo.")

    class Meta:
        model = InterestCampaign
        fields = ('name', 'interest_areas', 'subject', 'body')

    class Media:
        js = ('https://cdn.jsdelivr.net/npm/tinymce@7.6.0/tinymce.min.js',
              'admin/js/email_wysiwyg.js')


@admin.register(InterestCampaign)
class InterestCampaignAdmin(admin.ModelAdmin):
    form = InterestCampaignForm
    list_display = ('name', 'aree', 'destinatari', 'sent_at', 'sent_count')
    search_fields = ('name',)
    filter_horizontal = ('interest_areas',)
    readonly_fields = ('destinatari', 'sent_at', 'sent_by', 'sent_count')
    fieldsets = (
        (None, {'fields': ('name', 'interest_areas', 'destinatari')}),
        ('Contenuto email', {'fields': ('subject', 'body')}),
        ('Invio', {'fields': ('sent_at', 'sent_by', 'sent_count')}),
    )
    actions = ['action_prova', 'action_invia']

    @admin.display(description='Aree')
    def aree(self, obj):
        return ', '.join(obj.interest_areas.values_list('name', flat=True))

    @admin.display(description='Destinatari')
    def destinatari(self, obj):
        if not obj or not obj.pk:
            return '—'
        from sponsors.rubrica import destinatari_per_aree
        return len(destinatari_per_aree(obj.interest_areas.all()))

    @admin.action(description="Invia una PROVA a me")
    def action_prova(self, request, queryset):
        from contracts.tasks.notifications import send_interest_campaign
        for c in queryset:
            send_interest_campaign.delay(c.pk, test_to=request.user.email)
        self.message_user(request, f"Prova in invio a {request.user.email}.")

    @admin.action(description="INVIA a tutti i destinatari (una sola volta)")
    def action_invia(self, request, queryset):
        from django.contrib import messages
        from django.utils import timezone
        from contracts.tasks.notifications import send_interest_campaign
        partite = 0
        for c in queryset:
            # update condizionato: un doppio clic non la manda due volte
            if InterestCampaign.objects.filter(pk=c.pk, sent_at__isnull=True).update(
                    sent_at=timezone.now(), sent_by=request.user):
                send_interest_campaign.delay(c.pk)
                partite += 1
        saltate = queryset.count() - partite
        self.message_user(request, f"{partite} campagna/e in invio."
                          + (f" {saltate} già inviata/e: ignorata/e." if saltate else ''),
                          level=messages.WARNING if saltate else messages.SUCCESS)
```

Verificare che in cima a `sponsors/admin.py` ci siano `from django import forms` e `from core.admin_widgets import TranslatableJSONField` (`grep -n "^from django import forms\|TranslatableJSONField" sponsors/admin.py`); aggiungerli se mancano.

- [ ] **Step 6: Test verdi, task registrato**

Run: `pytest tests/test_rubrica_campagne.py tests/test_campagne_promozionali.py -v`
Expected: tutti passed

Run: `python -c "import django,os;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.development');django.setup();from config.celery import app;app.loader.import_default_modules();print('contracts.tasks.notifications.send_interest_campaign' in app.tasks)"`
Expected: `True`

- [ ] **Step 7: Commit**

```bash
git add contracts/tasks/notifications.py portal/views/campaigns.py portal/urls.py portal/templates/portal/campaign_unsubscribe.html sponsors/admin.py tests/test_rubrica_campagne.py locale/en/LC_MESSAGES/django.po locale/en/LC_MESSAGES/django.mo
git diff --cached --stat
git commit -F ~/msg_rubrica.txt   # "Rubrica: campagne per aree di interesse con prova e disiscrizione da tutto il marketing"
```

(Se `locale/*.mo` e' in `.gitignore`, togliere il `.mo` dal comando: controllare con `git check-ignore locale/en/LC_MESSAGES/django.mo`.)

---

### Task 9: Verifica finale, permessi staff e deploy (deploy SOLO con OK di Daniele)

**Files:** nessuno nuovo.

- [ ] **Step 1: Suite completa**

Run: `pytest tests/ -q`
Expected: nessun fallimento nuovo rispetto a `git stash`-free baseline (lanciare la stessa suite su `039c977c` se serve un confronto; i test del WIP altrui `tests/test_spazio_occupato_da_bozza.py` possono fallire per motivi non nostri: segnalarlo, non correggerlo).

- [ ] **Step 2: Prova manuale in locale (runserver, dati di test, MAI produzione)**

1. Creare 2 aree (Cardiologia, Oncologia).
2. Importare un CSV di 5 righe che contenga: una riga buona, una con area sbagliata, una con azienda simile a una esistente, una con email ripetuta, una senza email. Verificare l'anteprima (1 importabile, 4 errori con messaggi leggibili) e la conferma.
3. Trasferire un contatto e verificare: vecchia scheda "Uscito dal", nuova scheda con aree.
4. Creare una campagna su Cardiologia, "Invia una PROVA a me" (in dev l'email esce in console), poi "INVIA" e un secondo "INVIA" (deve dire "già inviata").
5. Aprire il link di disiscrizione dalla console e verificare la pagina e la riga in "Email escluse".

- [ ] **Step 3: Permessi dello staff**

Gli operatori non superuser vedono solo i modelli per cui hanno i permessi Django. In produzione, da Admin → Gruppi (o Utenti), dare allo staff: `view/add/change` su *Area di interesse* e *Campagna per aree di interesse*, `view/delete` su *Email esclusa dal marketing*. Verificare entrando con un utente operatore.

- [ ] **Step 4: Deploy (SOLO dopo OK esplicito di Daniele)**

Seguire `DEPLOY.md`. Punti obbligatori:
- `git status -sb` → solo i nostri commit davanti a `origin/main`; il WIP altrui resta NON committato.
- `git push`, poi sul server pull + rebuild di **tutti** i container che eseguono il codice: `docker compose up -d --build web celery_worker celery_beat`.
- Attendere il boot (`docker compose logs web` fino a "Booting worker"), poi verificare: migrazione `sponsors 0020` applicata, pagina `/admin/sponsors/interestarea/` raggiungibile, task `send_interest_campaign` registrato nel worker.
- Backup del DB PRIMA del deploy.
