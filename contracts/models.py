"""
Modelli dell'app Contracts.

Contract è il cuore del sistema: lega sponsor + evento + (stand|blocco) + righe.
ContractLine sono i singoli servizi acquistati nel contratto.

La logica di business critica (transizioni di stato, generazione scadenze,
cascata su stand/blocchi) è centralizzata nei metodi del modello.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from catalog.models import Service
from core.models import SoftDeleteModel, TimeStampedModel
from events.models import Event
from sponsors.models import Contact, Sponsor
from venues.models import Stand, StandBlock


class ContractStatus(models.TextChoices):
    DRAFT = 'draft', 'Bozza'
    SENT = 'sent', 'Inviato'
    PENDING_PAYMENT = 'pending_payment', 'In attesa pagamento'
    SIGNED = 'signed', 'Firmato'
    ACTIVE = 'active', 'Attivo'
    COMPLETED = 'completed', 'Completato'
    CANCELLED = 'cancelled', 'Annullato'


class ContractKind(models.TextChoices):
    MAIN = 'main', 'Principale'
    ADDON = 'addon', 'Addon ecommerce'
    ADDENDUM = 'addendum', 'Addendum'


class ContractOrigin(models.TextChoices):
    MANUAL = 'manual', 'Manuale'
    ECOMMERCE = 'ecommerce', 'Ecommerce'
    IMPORT = 'import', 'Importato'


class PaymentMethod(models.TextChoices):
    PAYPAL = 'paypal', 'PayPal'
    BANK_TRANSFER = 'bank_transfer', 'Bonifico'
    INSTALLMENTS = 'installments', 'Rateale'
    OTHER = 'other', 'Altro'


class Contract(SoftDeleteModel):
    """
    Contratto sponsor. Cuore del sistema.
    
    Stati:
        DRAFT → SENT → SIGNED → ACTIVE → COMPLETED
                                       → CANCELLED (in qualunque punto)
    
    Importanti regole di business:
    - stand_id e stand_block_id sono mutuamente esclusivi
    - I prezzi delle righe vengono "congelati" alla creazione
    - La transizione a SIGNED scatena: cascata stato stand/blocco + generazione scadenze
    """
    event = models.ForeignKey(
        Event,
        on_delete=models.PROTECT,
        related_name='contracts',
        verbose_name="Evento",
    )
    sponsor = models.ForeignKey(
        Sponsor,
        on_delete=models.PROTECT,
        related_name='contracts',
        verbose_name="Sponsor",
    )

    # Spazio espositivo: o stand singolo OPPURE blocco. Mai entrambi.
    stand = models.ForeignKey(
        Stand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contracts',
        verbose_name="Stand singolo",
    )
    stand_block = models.ForeignKey(
        StandBlock,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contracts',
        verbose_name="Blocco stand",
    )

    option_until = models.DateField(
        null=True,
        blank=True,
        verbose_name="Spazio opzionato fino al",
        help_text="Se valorizzata e non scaduta, lo spazio (stand/blocco) risulta "
                  "opzionato (riservato) per questo cliente anche in bozza, e non e proponibile "
                  "ad altri. Alla scadenza lo spazio torna disponibile.",
    )

    # Tipo di contratto: distingue main da addon ecommerce
    contract_kind = models.CharField(
        max_length=20,
        choices=ContractKind.choices,
        default=ContractKind.MAIN,
        verbose_name="Tipo contratto",
    )

    # Riferimento al contratto principale (solo per addon/addendum)
    parent_contract = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='child_contracts',
        verbose_name="Contratto principale",
        help_text="Per contratti addon, riferimento al main contract",
    )

    # Origine del contratto: come è stato creato
    origin = models.CharField(
        max_length=20,
        choices=ContractOrigin.choices,
        default=ContractOrigin.MANUAL,
        verbose_name="Origine",
    )

    # Lingua del contratto (per scelta template e PDF)
    language = models.CharField(
        max_length=2,
        default='it',
        verbose_name="Lingua",
    )

    contract_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Numero contratto",
        help_text="Generato dall'app, formato es. '2026-FE-001'",
    )

    sponsor_signer_contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='signed_contracts',
        verbose_name="Firmatario",
    )

    status = models.CharField(
        max_length=20,
        choices=ContractStatus.choices,
        default=ContractStatus.DRAFT,
        verbose_name="Stato",
    )

    # Date chiave
    issued_date = models.DateField(null=True, blank=True, verbose_name="Data emissione")
    sent_date = models.DateTimeField(null=True, blank=True, verbose_name="Inviato il")
    signed_date = models.DateField(null=True, blank=True, verbose_name="Data firma")
    cancelled_date = models.DateTimeField(null=True, blank=True, verbose_name="Annullato il")
    cancellation_reason = models.TextField(blank=True, verbose_name="Motivo annullamento")

    # Importi (calcolati ma salvati per snapshot)
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Imponibile",
    )
    vat_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="IVA",
    )
    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Totale",
    )

    # Pagamento
    payment_method = models.CharField(
        max_length=50,
        choices=PaymentMethod.choices,
        blank=True,
        verbose_name="Modalità pagamento",
    )
    payment_terms = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Termini pagamento",
        help_text="Es. '30 gg data fattura'",
    )
    payment_installments = models.IntegerField(
        default=1,
        verbose_name="Numero rate",
    )

    # IVA contratto
    vat_applicable = models.BooleanField(default=True, verbose_name="IVA applicabile")
    vat_exemption_reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Motivo esenzione IVA",
    )

    template_used = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Template usato",
        help_text="Es. ECM_2026, NON_ECM_2026, CUSTOM",
    )

    special_clauses = models.TextField(blank=True, verbose_name="Clausole speciali")

    quote_intro_text = models.TextField(
        blank=True,
        verbose_name="Testo lettera preventivo",
        help_text="Testo introduttivo della lettera di preventivo da inviare al cliente. "
                  "Lasciare vuoto se non serve. Il sistema aggiunge intestazione e riepilogo dati.",
    )

    letter_template = models.ForeignKey(
        'shared.LetterTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contracts',
        verbose_name="Template lettera preventivo",
        help_text="Template usato per generare la lettera di preventivo (al volo). "
                  "I segnaposti vengono compilati con i dati di questo contratto.",
    )

    deposit_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Acconto %",
        help_text="Percentuale di acconto (es. 30 per il 30%). Vuoto = pagamento unico (tutto a saldo).",
    )

    deposit_due_date_override = models.DateField(
        null=True,
        blank=True,
        verbose_name="Scadenza acconto (manuale)",
        help_text="Se vuoto, calcolata come data firma + giorni impostati nelle Impostazioni segreteria.",
    )
    balance_due_date_override = models.DateField(
        null=True,
        blank=True,
        verbose_name="Scadenza saldo (manuale)",
        help_text="Se vuoto, calcolata come inizio evento - giorni impostati nelle Impostazioni segreteria.",
    )

    stand_description_override = models.TextField(
        blank=True,
        verbose_name="Descrizione stand (preventivo, manuale)",
        help_text="Se compilata, sostituisce la descrizione dello stand nel preventivo di questo contratto. Vuota = usa la descrizione dello stand/blocco.",
    )

    # Override prezzo/sconto della riga STAND per questo contratto. Vuoti =
    # prezzo base dello stand/blocco senza sconto (la riga resta modificabile a mano).
    stand_price_override = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Prezzo stand (override)",
        help_text="Se valorizzato, sostituisce il prezzo base dello stand/blocco nella riga del contratto.",
    )
    stand_discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="Sconto stand (%)",
        help_text="Sconto percentuale (0-100) applicato alla riga stand.",
    )
    stand_discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Sconto stand (€)",
        help_text="Sconto in valore applicato alla riga stand.",
    )

    # Compliance regolatoria (dipende da evento+sponsor, quindi per-contratto)
    requires_aifa = models.BooleanField(
        default=False,
        verbose_name="Richiede AIFA (per questo evento)",
    )
    requires_svc_medtech = models.BooleanField(
        default=False,
        verbose_name="Richiede MEDTECH/SVC (per questo evento)",
    )
    internal_notes = models.TextField(
        blank=True,
        verbose_name="Note interne",
        help_text="Non vanno nel PDF, solo per il team",
    )

    class Meta:
        verbose_name = "Contratto"
        verbose_name_plural = "Contratti"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['contract_number']),
        ]

    def __str__(self):
        return f"{self.contract_number} · {self.sponsor.legal_name}"

    @property
    def vat_rate(self):
        """
        Aliquota IVA rappresentativa del contratto (la più comune tra le righe).
        Usata nei template contratto per mostrare "IVA (X%)" nell'allegato.
        Default: 22 se nessuna riga ha IVA valorizzata.
        """
        from collections import Counter
        rates = [line.vat_rate for line in self.lines.all() if line.vat_rate is not None]
        if not rates:
            return 22
        # Ritorna l'aliquota più comune (per evitare problemi se ci sono righe miste)
        most_common = Counter(rates).most_common(1)[0][0]
        return int(most_common)

    def _contratti_che_tengono(self, **filtro_spazio):
        """
        Contratti (diversi da self, non annullati) che 'tengono' lo spazio indicato:
        - stati SENT/SIGNED/ACTIVE/COMPLETED, OPPURE
        - DRAFT con opzione attiva (option_until >= oggi).
        I DRAFT senza opzione o con opzione scaduta NON tengono lo spazio.
        """
        from django.db.models import Q
        from django.utils import timezone
        oggi = timezone.now().date()
        tengono = (
            Q(status__in=[ContractStatus.SENT, ContractStatus.SIGNED,
                          ContractStatus.ACTIVE, ContractStatus.COMPLETED])
            | Q(status=ContractStatus.DRAFT, option_until__isnull=False,
                option_until__gte=oggi)
        )
        return (Contract.objects
                .filter(**filtro_spazio)
                .exclude(status=ContractStatus.CANCELLED)
                .exclude(pk=self.pk)
                .filter(tengono))

    def clean(self):
        """Validazione: stand e stand_block sono mutuamente esclusivi."""
        super().clean()
        if self.stand and self.stand_block:
            raise ValidationError(
                "Un contratto non può avere sia uno stand singolo che un blocco. "
                "Scegli uno dei due."
            )

        # Lo stand/blocco deve appartenere allo stesso evento del contratto
        if self.stand and self.stand.event_id != self.event_id:
            _ev_stand = self.stand.event.get_name() if self.stand.event_id else '-'
            _ev_contr = self.event.get_name() if self.event_id else '-'
            raise ValidationError({'stand': (
                f"Lo stand '{self.stand.code}' appartiene all'evento '{_ev_stand}', "
                f"ma questo contratto e' per l'evento '{_ev_contr}'. "
                f"Nella tendina dello stand digita il nome dell'evento "
                f"'{_ev_contr}' per vedere solo i suoi stand.")})

        # Uno stand che fa parte di un blocco NON e' vendibile singolarmente:
        # va venduto il blocco intero (oppure lo stand va tolto dal blocco).
        if self.stand and self.stand.stand_block_id:
            raise ValidationError({'stand': (
                f"Lo stand '{self.stand.code}' fa parte del blocco "
                f"'{self.stand.stand_block.code}' e non puo' essere venduto "
                f"singolarmente. Assegna il BLOCCO a questo contratto, oppure "
                f"togli lo stand dal blocco.")})
        if self.stand_block and self.stand_block.event_id != self.event_id:
            _evb = self.stand_block.event.get_name() if self.stand_block.event_id else '-'
            _evc = self.event.get_name() if self.event_id else '-'
            raise ValidationError({'stand_block': (
                f"Il blocco '{self.stand_block.code}' appartiene all'evento '{_evb}', "
                f"ma questo contratto e' per l'evento '{_evc}'. "
                f"Nella tendina del blocco digita il nome dell'evento "
                f"'{_evc}' per vedere solo i suoi blocchi.")})

        # Unicità stand: bloccato se un ALTRO contratto 'tiene' lo spazio
        # (SENT/firmato, oppure DRAFT con opzione attiva). Vedi _contratti_che_tengono.
        if self.stand:
            altro = self._contratti_che_tengono(stand=self.stand).first()
            if altro:
                raise ValidationError({'stand': (
                    f"Lo stand '{self.stand.code}' è già impegnato dal contratto "
                    f"{altro.contract_number or '(in creazione)'} "
                    f"({altro.sponsor}, stato: {altro.get_status_display()}"
                    f"{', opzionato fino al ' + altro.option_until.strftime('%d/%m/%Y') if altro.option_until else ''}). "
                    f"Annulla/libera quel contratto o scegli un altro stand.")})
        if self.stand_block:
            altro = self._contratti_che_tengono(stand_block=self.stand_block).first()
            if altro:
                raise ValidationError({'stand_block': (
                    f"Il blocco '{self.stand_block.code}' è già impegnato dal contratto "
                    f"{altro.contract_number or '(in creazione)'} "
                    f"({altro.sponsor}, stato: {altro.get_status_display()}"
                    f"{', opzionato fino al ' + altro.option_until.strftime('%d/%m/%Y') if altro.option_until else ''}). "
                    f"Annulla/libera quel contratto o scegli un altro blocco.")})

        # Validazioni parent_contract
        if self.contract_kind == ContractKind.MAIN and self.parent_contract:
            raise ValidationError({
                'parent_contract': "Un contratto principale non può avere un parent.",
            })
        if self.contract_kind in [ContractKind.ADDON, ContractKind.ADDENDUM]:
            if not self.parent_contract:
                raise ValidationError({
                    'parent_contract': f"Un contratto {self.contract_kind} richiede un parent contract.",
                })
            # Il parent deve essere un main dello stesso sponsor e evento
            if self.parent_contract.contract_kind != ContractKind.MAIN:
                raise ValidationError({
                    'parent_contract': "Il parent deve essere un contratto principale.",
                })
            if self.parent_contract.sponsor_id != self.sponsor_id:
                raise ValidationError({
                    'parent_contract': "Il parent deve essere dello stesso sponsor.",
                })
            if self.parent_contract.event_id != self.event_id:
                raise ValidationError({
                    'parent_contract': "Il parent deve essere dello stesso evento.",
                })

    # ---------------------------------------------------------------------
    # Calcolo importi
    # ---------------------------------------------------------------------

    def _generate_contract_number(self):
        """Genera il numero contratto formato SIGLA-AA-NNN (es. HIFU-26-001).

        - SIGLA: event.code (maiuscolo). Se vuota, fallback dallo slug.
        - AA: ultime 2 cifre dell'anno dell'evento.
        - NNN: progressivo a 3 cifre, riparte da 1 per ogni evento/anno.
          Oltre 999 passa a 4 cifre automaticamente.
        """
        from datetime import date

        sigla = (getattr(self.event, 'code', '') or '').strip().upper()
        if not sigla:
            base = (self.event.slug or 'EV').replace('-', '')
            sigla = base[:4].upper() or 'EV'

        anno_full = self.event.start_date.year if self.event.start_date else date.today().year
        anno = f"{anno_full % 100:02d}"

        prefix = f"{sigla}-{anno}-"

        with transaction.atomic():
            ultimo = (
                Contract.all_objects
                .filter(event=self.event, contract_number__startswith=prefix)
                .order_by('-contract_number')
                .values_list('contract_number', flat=True)
                .first()
            )
            if ultimo:
                try:
                    n = int(ultimo.rsplit('-', 1)[1]) + 1
                except (IndexError, ValueError):
                    n = 1
            else:
                n = 1
            while True:
                candidato = f"{prefix}{n:03d}"
                if not Contract.all_objects.filter(contract_number=candidato).exists():
                    return candidato
                n += 1

    def save(self, *args, **kwargs):
        from django.db import IntegrityError

        # In CREAZIONE eredita la lingua dal cliente (contatto principale) se
        # l'operatore l'ha lasciata sul default 'it'. Sull'edit non si tocca.
        if self._state.adding and (self.language or 'it') == 'it' and self.sponsor_id:
            try:
                _c = self.sponsor.primary_contact or self.sponsor.contacts.first()
                _pl = getattr(_c, 'preferred_language', None) if _c else None
                if _pl in ('it', 'en'):
                    self.language = _pl
            except Exception:
                pass

        # Cambio LINGUA su un contratto esistente: gli snapshot delle righe
        # (nome/descrizione servizio, etichetta stand) vanno ri-tradotti,
        # altrimenti il preventivo resta nella lingua vecchia.
        _riallinea_lingua = False
        if not self._state.adding and self.pk:
            _prev_lang = (type(self).all_objects.filter(pk=self.pk)
                          .values_list('language', flat=True).first())
            _riallinea_lingua = bool(_prev_lang) and _prev_lang != (self.language or _prev_lang)

        # Numero gia' presente (o esplicito): salvataggio normale.
        if self.contract_number:
            super().save(*args, **kwargs)
            self._sync_option_venue(kwargs.get('update_fields'))
            # Sincronizza la scadenza-opzione anche sui contratti esistenti:
            # quando il preventivo viene confermato (status -> SIGNED) o l'opzione
            # viene rimossa, la Deadline 'scadenza_opzione' pending viene eliminata.
            self._sync_option_deadline(kwargs.get('update_fields'))
            if _riallinea_lingua and self.status in (
                    ContractStatus.DRAFT, ContractStatus.SENT,
                    ContractStatus.PENDING_PAYMENT):
                self._riallinea_snapshot_lingua()
            return

        # Numero assente: genera in automatico (vale anche per ADDON/ADDENDUM).
        # Retry su IntegrityError per gestire creazioni simultanee (race):
        # se due contratti generano lo stesso numero nello stesso istante, il
        # secondo rigenera e riprova invece di andare in crash.
        last_err = None
        for _ in range(6):
            self.contract_number = self._generate_contract_number()
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                self._sync_option_venue(kwargs.get('update_fields'))
                self._sync_option_deadline(kwargs.get('update_fields'))
                self._sync_stand_line(kwargs.get('update_fields'))
                return
            except IntegrityError as e:
                if 'contract_number' not in str(e).lower():
                    raise
                last_err = e
                self.contract_number = ''  # forza una nuova generazione
        # Esauriti i tentativi: rilancia l'ultimo errore.
        raise last_err

    def _sync_option_venue(self, update_fields=None):
        """
        Dopo il salvataggio di una BOZZA con opzione (option_until), aggiorna lo
        stato dello stand/blocco cosi' risulta riservato gia' in bozza.
        Guardie:
        - salta i salvataggi parziali dei soli totali (recalculate_totals) per
          evitare lavoro inutile e ricorsioni;
        - agisce solo se c'e' uno stand/blocco e un'opzione impostata.
        """
        from contracts.models import ContractStatus
        # salta i save mirati ai soli totali / campi non rilevanti
        if update_fields is not None:
            campi = set(update_fields)
            rilevanti = {'status', 'option_until', 'stand', 'stand_block'}
            if not (campi & rilevanti):
                return
        if self.status != ContractStatus.DRAFT:
            return
        if not self.option_until:
            return
        if not (self.stand_id or self.stand_block_id):
            return
        try:
            self._update_venue_status()
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Errore aggiornamento stato spazio per opzione, contract %s",
                getattr(self, 'contract_number', '?'),
            )

    def _sync_option_deadline(self, update_fields=None):
        """
        Sincronizza la Deadline 'scadenza_opzione' con option_until.
        - crea/aggiorna se: DRAFT + option_until + spazio assegnato;
        - elimina (se pending) se: opzione tolta o contratto non piu' DRAFT.
        Idempotente. La Deadline opzione e' una sola per contratto.
        """
        from contracts.models import ContractStatus, Deadline, DeadlineStatus

        # salta i save mirati ai soli totali / campi non rilevanti
        if update_fields is not None:
            campi = set(update_fields)
            rilevanti = {'status', 'option_until', 'stand', 'stand_block'}
            if not (campi & rilevanti):
                return

        if not self.pk:
            return

        try:
            esistente = self.deadlines.filter(deadline_type='scadenza_opzione').first()

            vuole_opzione = (
                self.status == ContractStatus.DRAFT
                and self.option_until is not None
                and (self.stand_id or self.stand_block_id)
            )

            if vuole_opzione:
                if esistente:
                    # aggiorna la data se cambiata (e riporta a pending se serve)
                    if esistente.due_date != self.option_until:
                        esistente.due_date = self.option_until
                        if esistente.status == DeadlineStatus.OVERDUE:
                            esistente.status = DeadlineStatus.PENDING
                        esistente.save(update_fields=['due_date', 'status', 'updated_at'])
                else:
                    Deadline.objects.create(
                        contract=self,
                        contract_line=None,
                        deadline_template=None,
                        deadline_type='scadenza_opzione',
                        title="Scadenza opzione spazio",
                        description="Promemoria scadenza dell'opzione sullo spazio espositivo.",
                        due_date=self.option_until,
                    )
            else:
                # opzione non piu' valida: elimina la Deadline opzione se ancora pending
                if esistente and esistente.status in (
                    DeadlineStatus.PENDING, DeadlineStatus.REMINDER_SENT, DeadlineStatus.OVERDUE
                ):
                    esistente.delete()
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Errore sincronizzazione Deadline opzione, contract %s",
                getattr(self, 'contract_number', '?'),
            )

    def _sync_stand_line(self, update_fields=None):
        """
        Sincronizza la ContractLine 'stand' col stand/blocco del contratto.
          - crea/aggiorna se c'e' stand/blocco e la riga non esiste (o e' di
            uno stand/blocco diverso);
          - elimina se non c'e' piu' ne' stand ne' blocco.
        Idempotente sul marker (notes='stand:CODE' / 'block:CODE').
        """
        # salta i save mirati ai soli totali (evita loop)
        if update_fields is not None:
            campi = set(update_fields)
            rilevanti = {'stand', 'stand_block', 'event'}
            if not (campi & rilevanti):
                return

        if not self.pk:
            return

        try:
            from contracts.services.stand_line import (
                _stand_price_and_label, genera_riga_da_stand,
            )

            # determino il marker atteso (se c'e' stand/blocco)
            marker_atteso = None
            if self.stand_id or self.stand_block_id:
                try:
                    _p, _l, marker_atteso, _d, _t = _stand_price_and_label(self)
                except ValueError:
                    marker_atteso = None

            # rimuovo righe stand obsolete (di stand/blocchi NON piu' assegnati)
            obsolete = self.lines.filter(
                models.Q(notes__startswith='stand:') | models.Q(notes__startswith='block:')
            )
            if marker_atteso:
                obsolete = obsolete.exclude(notes=marker_atteso)
            for r in obsolete:
                r.delete()  # delete -> ContractLine.delete() ricalcola i totali

            # se ho stand/blocco, crea la riga se non esiste (idempotente)
            if marker_atteso:
                genera_riga_da_stand(self)
                # gli esiti: 'creata' (ok), 'gia_presente' (ok), 'no_prezzo' (lo logghiamo)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Errore sincronizzazione riga stand, contract %s",
                getattr(self, 'contract_number', '?'),
            )

    def recalculate_totals(self, save=True):
        """
        Ricalcola subtotal, vat_amount e total dalla somma delle righe.
        Va chiamato dopo modifica righe contratto.
        """
        lines = self.lines.all()
        subtotal = sum((line.line_subtotal for line in lines), Decimal('0.00'))
        vat = sum((line.line_vat for line in lines), Decimal('0.00'))

        self.subtotal = subtotal
        self.vat_amount = vat if self.vat_applicable else Decimal('0.00')
        self.total = self.subtotal + self.vat_amount

        if save:
            self.save(update_fields=['subtotal', 'vat_amount', 'total', 'updated_at'])

    # ---------------------------------------------------------------------
    @property
    def lines_riepilogo(self):
        """Righe per il RIEPILOGO servizi (portale/documenti): prima le righe
        valorizzate economicamente (importo decrescente), poi in cascata le
        altre (incluse/a costo zero, nell'ordine originale)."""
        from decimal import Decimal
        return sorted(
            self.lines.all(),
            key=lambda l: ((l.line_subtotal or Decimal('0')) <= 0,
                           -(l.line_subtotal or Decimal('0'))),
        )

    # Piano pagamento (acconto/saldo) - calcolato al volo, IVA inclusa
    @property
    def deposit_amount(self):
        """Importo acconto (IVA inclusa). 0 se nessuna percentuale impostata."""
        from decimal import Decimal
        if not self.deposit_percent:
            return Decimal('0.00')
        return (self.total * self.deposit_percent / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def balance_amount(self):
        """Importo saldo (IVA inclusa) = totale - acconto. Se nessun acconto, = totale."""
        return (self.total - self.deposit_amount)

    @property
    def deposit_due_date(self):
        """Scadenza acconto: override manuale se presente, altrimenti
        data firma + giorni (OrganizerSettings). None se non firmato e niente override."""
        if self.deposit_due_date_override:
            return self.deposit_due_date_override
        from datetime import timedelta
        from core.models import OrganizerSettings
        if not self.signed_date:
            return None
        days = OrganizerSettings.load().payment_deposit_days_after_signing or 0
        return self.signed_date + timedelta(days=days)

    @property
    def balance_due_date(self):
        """Scadenza saldo: override manuale se presente, altrimenti
        inizio evento - giorni (OrganizerSettings). None se manca data evento e niente override."""
        if self.balance_due_date_override:
            return self.balance_due_date_override
        from datetime import timedelta
        from core.models import OrganizerSettings
        start = getattr(self.event, 'start_date', None)
        if not start:
            return None
        days = OrganizerSettings.load().payment_balance_days_before_event or 0
        return start - timedelta(days=days)

    @property
    def has_deposit(self):
        """True se e' previsto un acconto (percentuale impostata e > 0)."""
        return bool(self.deposit_percent and self.deposit_percent > 0)

    # ---------------------------------------------------------------------
    # Transizioni di stato
    # ---------------------------------------------------------------------

    @transaction.atomic
    def mark_as_sent(self):
        """Passa da DRAFT a SENT. Genera automaticamente il PDF (skip per ADDON)."""
        if self.status != ContractStatus.DRAFT:
            raise ValidationError(
                f"Non posso inviare un contratto in stato '{self.get_status_display()}'."
            )

        self.status = ContractStatus.SENT
        self.sent_date = timezone.now()
        self.save(update_fields=['status', 'sent_date', 'updated_at'])

        # Stand/blocco passa a 'reserved'
        self._update_venue_status()

        # Nuovo flusso preventivo -> domanda di ammissione:
        # all'invio del preventivo NON si genera piu' alcun PDF "contratto".

    @transaction.atomic
    def mark_as_signed(self, signed_date=None):
        """
        Passa a SIGNED.
        Effetti collaterali:
        - Stand/blocco passa a 'assigned'
        - Vengono generate le scadenze automatiche dai DeadlineTemplate
        """
        if self.status not in [ContractStatus.DRAFT, ContractStatus.SENT, ContractStatus.PENDING_PAYMENT]:
            raise ValidationError(
                f"Non posso firmare un contratto in stato '{self.get_status_display()}'."
            )

        self.status = ContractStatus.SIGNED
        self.signed_date = signed_date or timezone.now().date()
        self.save(update_fields=['status', 'signed_date', 'updated_at'])

        # Cascata stato venue (solo se contratto ha stand)
        self._update_venue_status()

        # Genera scadenze concrete dai template
        self._generate_deadlines()

        # Genera le scadenze di pagamento (acconto/saldo) per i reminder automatici
        self._generate_payment_deadlines()

        # Scadenza per la restituzione del contratto firmato (upload nel portale)
        self._generate_signed_contract_deadline()

        # Notifica email di conferma (sincrona in dev con EAGER=True).
        try:
            from contracts.tasks.notifications import send_contract_signed_notification
            send_contract_signed_notification.delay(self.id)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Invio notifica firma fallito per contract %s", self.id
            )

    @transaction.atomic
    def mark_as_pending_payment(self):
        """
        Per contratti addon ecommerce: dopo checkout, in attesa pagamento.
        Da DRAFT a PENDING_PAYMENT.
        """
        if self.status != ContractStatus.DRAFT:
            raise ValidationError(
                f"Non posso mettere in attesa pagamento un contratto in stato "
                f"'{self.get_status_display()}'."
            )
        if self.contract_kind != ContractKind.ADDON:
            raise ValidationError(
                "Lo stato pending_payment è solo per contratti addon ecommerce."
            )

        self.status = ContractStatus.PENDING_PAYMENT
        self.save(update_fields=['status', 'updated_at'])

    @transaction.atomic
    def mark_payment_succeeded(self):
        """
        Per addon ecommerce: pagamento ricevuto, contratto firmato automaticamente.
        Idempotente: se già signed, non fa nulla.
        """
        if self.status == ContractStatus.SIGNED:
            return  # già processato (idempotency)

        if self.status != ContractStatus.PENDING_PAYMENT:
            raise ValidationError(
                f"Non posso confermare pagamento per contratto in stato "
                f"'{self.get_status_display()}'."
            )

        self.mark_as_signed()

    @transaction.atomic
    def mark_as_active(self):
        """Passa a ACTIVE (es. quando inizia operativamente l'evento)."""
        if self.status != ContractStatus.SIGNED:
            raise ValidationError(
                "Solo un contratto firmato può diventare attivo."
            )
        self.status = ContractStatus.ACTIVE
        self.save(update_fields=['status', 'updated_at'])

    @transaction.atomic
    def mark_as_completed(self):
        """Passa a COMPLETED (evento concluso)."""
        if self.status not in [ContractStatus.SIGNED, ContractStatus.ACTIVE]:
            raise ValidationError(
                "Solo contratti firmati o attivi possono essere completati."
            )
        self.status = ContractStatus.COMPLETED
        self.save(update_fields=['status', 'updated_at'])

    @transaction.atomic
    def cancel(self, reason=''):
        """Annulla il contratto. Effetto: stand/blocco torna disponibile."""
        if self.status == ContractStatus.CANCELLED:
            return

        self.status = ContractStatus.CANCELLED
        self.cancelled_date = timezone.now()
        self.cancellation_reason = reason
        self.save(update_fields=[
            'status', 'cancelled_date', 'cancellation_reason', 'updated_at'
        ])

        # Libera lo stand/blocco
        self._update_venue_status()

        # Le scadenze di un contratto annullato non sono piu' dovute: le esonero.
        self.deadlines.filter(
            status__in=[DeadlineStatus.PENDING, DeadlineStatus.REMINDER_SENT,
                        DeadlineStatus.OVERDUE]
        ).update(status=DeadlineStatus.WAIVED)

        # I file inviati dal cliente per un contratto annullato vengono rimossi
        # (soft-delete: i record restano recuperabili lato admin).
        from django.contrib.contenttypes.models import ContentType
        from shared.models import Document
        _dl_ct = ContentType.objects.get_for_model(Deadline)
        Document.objects.filter(
            content_type=_dl_ct,
            object_id__in=self.deadlines.values_list('id', flat=True),
            deleted_at__isnull=True,
        ).update(deleted_at=timezone.now())

    def delete(self, using=None, keep_parents=False, hard=False):
        """Soft-delete del contratto. Oltre a nasconderlo, LIBERA lo stand/blocco
        assegnato: la rivalutazione (update_status_from_contract) esclude i
        contratti con deleted_at valorizzato, quindi lo spazio torna disponibile.
        Cosi' cancellare un preventivo libera lo stand esattamente come annullarlo.
        I servizi a numero limitato si liberano da soli (quantity_committed
        ignora i contratti cancellati/soft-deleted)."""
        stand = self.stand
        block = self.stand_block
        super().delete(using=using, keep_parents=keep_parents, hard=hard)
        try:
            if stand:
                stand.update_status_from_contract()
            elif block:
                block.update_status_from_contract()
        except Exception:
            pass

    # ---------------------------------------------------------------------
    # Helper privati
    # ---------------------------------------------------------------------

    def _update_venue_status(self):
        """Aggiorna lo stato dello stand o del blocco assegnato."""
        if self.stand:
            self.stand.update_status_from_contract()
        elif self.stand_block:
            self.stand_block.update_status_from_contract()

    def _generate_deadlines(self):
        """
        Genera record Deadline concreti dai DeadlineTemplate dei servizi
        venduti (solo quelli con triggers_deadlines=True).
        Idempotente: non duplica scadenze già esistenti.
        """
        from datetime import timedelta

        # Senza data evento non possiamo calcolare le scadenze: usciamo senza
        # errori (i signal che chiamano questo metodo non devono mai far
        # fallire un salvataggio).
        event = getattr(self, 'event', None)
        if not event or not event.start_date:
            return

        for line in self.lines.select_related('service').all():
            service = line.service
            if not service.triggers_deadlines:
                continue

            for template in service.deadline_templates.filter(is_active=True):
                # Evita duplicati se la firma viene ripetuta
                already_exists = self.deadlines.filter(
                    deadline_type=template.deadline_type,
                    contract_line=line,
                ).exists()
                if already_exists:
                    continue

                due_date = self.event.start_date - timedelta(days=template.days_before_event)
                Deadline.objects.create(
                    contract=self,
                    contract_line=line,
                    deadline_template=template,
                    deadline_type=template.deadline_type,
                    title=template.title,
                    description=template.description,
                    due_date=due_date,
                    submission_kind=getattr(template, 'submission_kind', 'file'),
                    content_schema=[
                        {
                            'key': f.key,
                            'label': f.label,
                            'type': f.field_type,
                            'required': f.required,
                            'help_text': f.help_text,
                        }
                        for f in template.content_fields.all().order_by('display_order')
                    ],
                )

    def reconcile_payment_deadlines(self):
        """Marca Ricevute le scadenze di pagamento coperte dagli incassi
        registrati (status SUCCEEDED). Chiamata al salvataggio di un Payment."""
        from decimal import Decimal
        from django.db.models import Sum
        from contracts.payments import Payment, PaymentStatus
        paid = (Payment.objects
                .filter(contract=self, status=PaymentStatus.SUCCEEDED)
                .aggregate(s=Sum('amount_gross'))['s'] or Decimal('0'))
        dep = self.deposit_amount or Decimal('0')
        tot = self.total or Decimal('0')

        def _close(dtype):
            dl = self.deadlines.filter(deadline_type=dtype).first()
            if dl and dl.status != DeadlineStatus.RECEIVED:
                dl.mark_as_received()

        if dep and paid >= dep:
            _close('pagamento_acconto')
        if tot and paid >= tot:
            _close('pagamento_acconto')
            _close('pagamento_saldo')

    def _generate_payment_deadlines(self):
        """
        Crea le scadenze di PAGAMENTO (acconto/saldo) per abilitare i reminder
        automatici. Idempotente: non duplica scadenze gia' presenti.
        Le date vengono dalle property deposit_due_date / balance_due_date.
        Si collega al DeadlineTemplate deadline_type='pagamento' se esiste
        (porta reminder_days_before e notify_roles).
        """
        # Gli addon ecommerce sono pagati subito al checkout: nessuna scadenza "da pagare".
        if self.contract_kind == ContractKind.ADDON:
            return
        from contracts.models import Deadline

        # template pagamento (opzionale): se c'e', le sue regole (7/3 gg, ruoli) valgono
        pay_template = None
        try:
            from catalog.models import DeadlineTemplate
            pay_template = DeadlineTemplate.objects.filter(
                deadline_type='pagamento', is_active=True
            ).first()
        except Exception:
            pay_template = None

        def _crea(deadline_type, title, due_date):
            if not due_date:
                return
            # idempotenza: non ricreare la stessa scadenza di pagamento
            if self.deadlines.filter(deadline_type=deadline_type, contract_line__isnull=True).exists():
                return
            Deadline.objects.create(
                contract=self,
                contract_line=None,
                deadline_template=pay_template,
                deadline_type=deadline_type,
                title=title,
                description="",
                due_date=due_date,
            )

        # Acconto solo se previsto
        if self.has_deposit:
            _crea('pagamento_acconto', "Scadenza acconto", self.deposit_due_date)
        # Saldo sempre (se c'e' una data calcolabile)
        _crea('pagamento_saldo', "Scadenza saldo", self.balance_due_date)

    def _generate_signed_contract_deadline(self, giorni=10):
        """Crea la scadenza 'Invio contratto firmato' (solo contratti MAIN).

        Il cliente deve restituire firmato il documento ricevuto alla
        conferma: il contratto di sponsorizzazione (eventi non-ECM) o la
        domanda di ammissione (eventi ECM). L'upload avviene nel portale,
        sezione Materiali; la scadenza entra nel giro standard di reminder
        (T-10/T-3/T-0) e solleciti. Idempotente."""
        from datetime import timedelta
        if self.contract_kind != ContractKind.MAIN:
            return
        if self.deadlines.filter(deadline_type='contratto_firmato').exists():
            return
        try:
            from events.models import EventType
            is_ecm = getattr(self.event, 'event_type', None) == EventType.ECM
        except Exception:
            is_ecm = False
        titolo = ("Invio domanda di ammissione firmata" if is_ecm
                  else "Invio contratto firmato")
        descrizione = (
            "Carica qui la copia firmata (PDF o scansione leggibile) del "
            "documento che hai ricevuto alla conferma del preventivo."
        )
        base = self.signed_date or timezone.now().date()
        Deadline.objects.create(
            contract=self,
            deadline_type='contratto_firmato',
            title=titolo,
            description=descrizione,
            due_date=base + timedelta(days=giorni),
        )

    def _riallinea_snapshot_lingua(self, apply=True):
        """Ri-traduce gli snapshot delle righe nella lingua del contratto.

        Tocca solo le righe il cui snapshot corrisponde ancora al nome (o alla
        descrizione) del servizio in UNA delle lingue disponibili — quelli
        personalizzati a mano dall'operatore restano intatti. La riga stand
        (marcatore 'stand:'/'block:' nelle note) viene rietichettata dalla
        stessa logica che l'ha creata. Con apply=False non scrive nulla.
        Ritorna la lista dei cambi: (line_id, campo, vecchio, nuovo)."""
        lang = self.language or 'it'
        cambi = []

        # Riga stand/blocco: etichetta e descrizione rigenerate per lingua
        try:
            from contracts.services.stand_line import _stand_price_and_label
            _, label, marker, descrizione, _tipo = _stand_price_and_label(self)
            for ln in self.lines.filter(notes__contains=marker):
                if ln.service_name_snapshot != label:
                    cambi.append((ln.pk, 'service_name_snapshot',
                                  ln.service_name_snapshot, label))
                    if apply:
                        type(ln).objects.filter(pk=ln.pk).update(
                            service_name_snapshot=label,
                            service_description_snapshot=descrizione,
                            updated_at=timezone.now())
        except ValueError:
            pass  # nessuno stand/blocco assegnato

        for ln in self.lines.select_related('service'):
            note = ln.notes or ''
            if not ln.service_id or 'stand:' in note or 'block:' in note:
                continue
            campi = {}
            nomi = ln.service.name if isinstance(ln.service.name, dict) else {}
            nuovo_nome = ln.service.translated('name', lang) or ''
            if (nuovo_nome and nuovo_nome != ln.service_name_snapshot
                    and ln.service_name_snapshot in set(nomi.values())):
                campi['service_name_snapshot'] = nuovo_nome
                cambi.append((ln.pk, 'service_name_snapshot',
                              ln.service_name_snapshot, nuovo_nome))
            descr = (ln.service.description
                     if isinstance(ln.service.description, dict) else {})
            nuova_desc = ln.service.translated('description', lang) or ''
            if (nuova_desc and nuova_desc != ln.service_description_snapshot
                    and ln.service_description_snapshot in set(descr.values())):
                campi['service_description_snapshot'] = nuova_desc
                cambi.append((ln.pk, 'service_description_snapshot',
                              ln.service_description_snapshot, nuova_desc))
            if campi and apply:
                campi['updated_at'] = timezone.now()
                type(ln).objects.filter(pk=ln.pk).update(**campi)
        return cambi


class ContractLine(TimeStampedModel):
    """
    Riga di un contratto: un servizio acquistato in una certa quantità.
    
    I prezzi vengono COPIATI dal Service al momento della creazione, così
    se il listino cambia i contratti firmati restano congelati.
    """
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name="Contratto",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name='contract_lines',
        verbose_name="Servizio",
    )

    # Snapshot servizio
    service_name_snapshot = models.CharField(max_length=255, verbose_name="Nome servizio")
    service_description_snapshot = models.TextField(blank=True, verbose_name="Descrizione")
    service_variant = models.ForeignKey(
        'catalog.ServiceVariant',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='variant_lines',
        verbose_name="Variante",
    )
    variant_label_snapshot = models.CharField(
        max_length=120, blank=True, verbose_name="Variante (etichetta)")

    quantity = models.IntegerField(
        default=1,
        verbose_name="Quantità",
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,  # eredita da service.base_price se vuoto (vedi save)
        blank=True,
        verbose_name="Prezzo unitario",
        help_text="Lascia vuoto per usare il prezzo standard del servizio.",
    )

    # Sconti
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Sconto %",
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Sconto importo",
    )

    # Totali calcolati e salvati
    line_subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Imponibile riga",
    )
    vat_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('22.00'),
        verbose_name="IVA %",
    )
    line_vat = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="IVA riga",
    )
    line_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Totale riga",
    )

    notes = models.TextField(blank=True, verbose_name="Note riga")
    display_order = models.IntegerField(default=0, verbose_name="Ordine")

    class Meta:
        verbose_name = "Riga contratto"
        verbose_name_plural = "Righe contratto"
        ordering = ['contract', 'display_order']

    def __str__(self):
        return f"{self.service_name_snapshot} × {self.quantity}"

    @property
    def variant_label_display(self):
        """Etichetta variante nella lingua attiva (fallback: snapshot)."""
        if self.service_variant_id:
            try:
                lbl = self.service_variant.label_display()
                if lbl:
                    return lbl
            except Exception:
                pass
        return self.variant_label_snapshot

    @property
    def service_name_display(self):
        """Nome servizio nella lingua attiva del portale (fallback: snapshot)."""
        if self.service_id:
            try:
                nome = self.service.translated('name')
                if nome:
                    return nome
            except Exception:
                pass
        return self.service_name_snapshot

    @property
    def is_included(self):
        """True se la riga e' un servizio incluso/accessorio aggiunto
        automaticamente da un servizio padre. Riconosciuta dal marker
        '[incluso:<parent_code>><sub_code>]' messo in notes da
        _aggiungi_servizi_inclusi."""
        return '[incluso:' in (self.notes or '')

    def clean(self):
        from django.db.models import Sum
        super().clean()
        if self.quantity < 1:
            raise ValidationError({'quantity': "La quantità deve essere almeno 1."})
        if self.discount_percent < 0 or self.discount_percent > 100:
            raise ValidationError({'discount_percent': "Lo sconto % deve essere 0-100."})
        # Coerenza evento: il servizio deve appartenere all'evento del contratto
        if (self.service_id and self.contract_id
                and self.service.event_id != self.contract.event_id):
            try:
                _ev_serv = self.service.event.get_name()
            except Exception:
                _ev_serv = '?'
            try:
                _ev_contr = self.contract.event.get_name()
            except Exception:
                _ev_contr = '?'
            raise ValidationError({'service': (
                f"Il servizio '{self.service.code}' appartiene all'evento "
                f"'{_ev_serv}', ma questo contratto e' per l'evento '{_ev_contr}'. "
                f"Nella tendina del servizio digita il nome dell'evento "
                f"'{_ev_contr}' per vedere solo i suoi servizi.")})

        if not self.service_id:
            return
        contract_id = self.contract_id

        # La variante scelta deve appartenere al servizio della riga.
        if self.service_variant_id and self.service_variant.service_id != self.service_id:
            raise ValidationError({'service_variant':
                "La variante selezionata non appartiene a questo servizio."})

        # Quantità massima per riga (campo 'Quantità massima' del servizio).
        # Es. servizio unico (muletto): max_quantity=1 -> non se ne possono mettere 2.
        mq = getattr(self.service, 'max_quantity', None)
        if mq is not None and (self.quantity or 0) > mq:
            raise ValidationError({'quantity':
                f"«{self.service.translated('name', 'it')}»: quantità massima consentita "
                f"per riga = {mq}. Hai inserito {self.quantity}."})

        # Disponibilità della VARIANTE (ha scorte proprie, es. "restano 10").
        if self.service_variant_id:
            v = self.service_variant
            v_avail = v.quantity_available(exclude_contract_id=contract_id)
            if v_avail is not None:
                already_v = 0
                if contract_id:
                    already_v = (v.variant_lines
                                 .filter(contract_id=contract_id)
                                 .exclude(pk=self.pk)
                                 .aggregate(t=Sum('quantity'))['t'] or 0)
                if (self.quantity or 0) + already_v > v_avail:
                    raise ValidationError({'quantity':
                        f"Variante «{v.label}» non disponibile in quantità "
                        f"sufficiente: richiesti {self.quantity}, disponibili {v_avail}."})

        # Disponibilità del SERVIZIO.
        avail = self.service.quantity_available(exclude_contract_id=contract_id)
        if avail is None:
            return  # illimitato
        already = 0
        if contract_id:
            already = (self.service.contract_lines
                       .filter(contract_id=contract_id)
                       .exclude(pk=self.pk)
                       .aggregate(t=Sum('quantity'))['t'] or 0)
        if (self.quantity or 0) + already > avail:
            raise ValidationError({'quantity':
                f"Servizio «{self.service.translated('name', 'it')}» non disponibile "
                f"in quantità sufficiente: richiesti {self.quantity}, disponibili {avail}."})

    @property
    def prezzo_listino(self):
        """Prezzo di listino (pieno) della riga × quantità: dal catalogo
        (variante o servizio) se disponibile, altrimenti dal prezzo unitario
        della riga. Non è mai inferiore al prezzo unitario impostato sulla riga."""
        unit = None
        notes = self.notes or ''
        # Riga stand/blocco: il listino è il prezzo base dello spazio assegnato.
        try:
            if notes.startswith('stand:') and self.contract.stand_id and self.contract.stand.base_price:
                unit = self.contract.stand.base_price
            elif notes.startswith('block:') and self.contract.stand_block_id:
                bp = getattr(self.contract.stand_block, 'effective_price', None)
                if bp:
                    unit = bp
        except Exception:
            unit = None
        if unit is None:
            try:
                if self.service_variant_id and self.service_variant and self.service_variant.base_price:
                    unit = self.service_variant.base_price
                elif self.service_id and self.service and self.service.base_price:
                    unit = self.service.base_price
            except Exception:
                unit = None
        if not unit or unit <= 0:
            unit = self.unit_price or Decimal('0')
        unit = max(unit, self.unit_price or Decimal('0'))
        return (unit * (self.quantity or 1)).quantize(Decimal('0.01'))

    @property
    def prezzo_listino_unit(self):
        """Prezzo di listino UNITARIO (per la colonna 'Prezzo'/'Pr. Unit.')."""
        q = self.quantity or 1
        try:
            return (self.prezzo_listino / q).quantize(Decimal('0.01')) if q else self.prezzo_listino
        except Exception:
            return self.prezzo_listino

    @property
    def prezzo_riservato(self):
        """Prezzo finale netto (imponibile) della riga, dopo sconti/override."""
        return self.line_subtotal

    @property
    def is_prezzo_revisionato(self):
        """True se il prezzo riservato è inferiore al listino (sconto o override).
        Esclude i servizi INCLUSI (a €0: vanno mostrati come 'Incluso', non scontati)."""
        try:
            if self.is_included:
                return False
            riservato = self.prezzo_riservato or Decimal('0')
            if riservato <= 0:
                return False
            return riservato < (self.prezzo_listino or Decimal('0'))
        except Exception:
            return False

    @property
    def is_sconto_esplicito(self):
        """True se la revisione del prezzo deriva da uno SCONTO esplicito (% o valore);
        False se deriva da un PREZZO OVERRIDE (prezzo unitario impostato sotto il listino)."""
        try:
            return bool((self.discount_percent or Decimal('0')) > 0
                        or (self.discount_amount or Decimal('0')) > 0)
        except Exception:
            return False

    @property
    def sconto_eur(self):
        """Valore dello sconto in euro (listino − riservato), 0 se non revisionato
        o se è un servizio incluso (a €0)."""
        if not self.is_prezzo_revisionato:
            return Decimal('0.00')
        d = (self.prezzo_listino or Decimal('0')) - (self.prezzo_riservato or Decimal('0'))
        return d if d > 0 else Decimal('0.00')

    def calculate_totals(self):
        """Calcola line_subtotal, line_vat, line_total dai dati base."""
        gross = self.unit_price * self.quantity
        # Applica sconto: prima percentuale, poi importo fisso
        if self.discount_percent:
            gross = gross * (Decimal('100') - self.discount_percent) / Decimal('100')
        if self.discount_amount:
            gross = gross - self.discount_amount

        gross = max(gross, Decimal('0.00'))
        self.line_subtotal = gross.quantize(Decimal('0.01'))

        if self.contract.vat_applicable:
            self.line_vat = (self.line_subtotal * self.vat_rate / Decimal('100')).quantize(
                Decimal('0.01')
            )
        else:
            self.line_vat = Decimal('0.00')

        self.line_total = self.line_subtotal + self.line_vat

    def save(self, *args, **kwargs):
        """
        Override save:
        - Popola snapshot dal Service alla prima creazione
        - Ricalcola totali riga
        - Ricalcola totali contratto dopo
        """
        is_new = self._state.adding

        # Snapshot al primo salvataggio, nella LINGUA DEL CONTRATTO (senza
        # lingua esplicita translated() userebbe la lingua dell'interfaccia
        # di chi salva — l'admin e' in italiano — e i preventivi EN
        # mostrerebbero i nomi in italiano).
        if is_new and self.service:
            _lang = getattr(self.contract, 'language', None) or 'it'
            if not self.service_name_snapshot:
                self.service_name_snapshot = self.service.translated('name', _lang)
            if not self.service_description_snapshot:
                self.service_description_snapshot = self.service.translated('description', _lang)
            # Variante scelta: salva l'etichetta e usa il suo prezzo.
            if self.service_variant_id and not self.variant_label_snapshot:
                self.variant_label_snapshot = self.service_variant.label
            if not self.unit_price:
                if self.service_variant_id and self.service_variant.base_price is not None:
                    self.unit_price = self.service_variant.base_price
                else:
                    # Prezzo base; logica avanzata (scaglioni) gestita a livello applicativo
                    self.unit_price = self.service.base_price
            if not self.vat_rate:
                self.vat_rate = self.service.vat_rate

        self.calculate_totals()
        super().save(*args, **kwargs)

        # Ricalcola totali contratto
        self.contract.recalculate_totals()

        # Auto-aggiunta dei servizi inclusi (solo riga 'padre' appena creata)
        if is_new and self.service_id and '[incluso:' not in (self.notes or ''):
            _aggiungi_servizi_inclusi(self)

    def delete(self, *args, **kwargs):
        contract = self.contract
        super().delete(*args, **kwargs)
        contract.recalculate_totals()


def _aggiungi_servizi_inclusi(parent_line):
    """Crea le righe dei 'servizi inclusi' (a EUR 0) del servizio della riga
    appena creata. Le scadenze si generano poi alla firma dai DeadlineTemplate
    del servizio incluso. Espansione a un solo livello. Idempotente (marcatore
    nelle note)."""
    service = getattr(parent_line, 'service', None)
    if not service:
        return
    try:
        inclusioni = list(service.inclusions.select_related('child').all())
    except Exception:
        return  # campo non ancora migrato: non bloccare
    parent_code = service.code or str(service.id)
    for inc in inclusioni:
        sub = inc.child
        sub_qta = inc.quantity or 1
        sub_code = sub.code or str(sub.id)
        marker = "[incluso:%s>%s]" % (parent_code, sub_code)
        if parent_line.contract.lines.filter(notes__contains=marker).exists():
            continue
        sub_line = ContractLine(
            contract=parent_line.contract,
            service=sub,
            service_name_snapshot=sub.translated(
                'name', getattr(parent_line.contract, 'language', None) or 'it'),
            quantity=sub_qta,
            notes=marker,
        )
        sub_line.save()
        if sub_line.unit_price and sub_line.unit_price != Decimal('0.00'):
            sub_line.unit_price = Decimal('0.00')
            sub_line.save()


class DeadlineStatus(models.TextChoices):
    PENDING = 'pending', 'Da fare'
    REMINDER_SENT = 'reminder_sent', 'Reminder inviato'
    RECEIVED = 'received', 'Ricevuto'
    OVERDUE = 'overdue', 'In ritardo'
    WAIVED = 'waived', 'Annullata'


class Deadline(TimeStampedModel):
    """
    Scadenza concreta di un contratto. Generata automaticamente da
    DeadlineTemplate quando un servizio viene venduto.
    """
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='deadlines',
        verbose_name="Contratto",
    )
    contract_line = models.ForeignKey(
        ContractLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deadlines',
        verbose_name="Riga contratto",
    )
    deadline_template = models.ForeignKey(
        'catalog.DeadlineTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Template",
    )

    # Snapshot
    deadline_type = models.CharField(max_length=50, verbose_name="Tipo")
    title = models.CharField(max_length=255, verbose_name="Titolo")
    description = models.TextField(blank=True, verbose_name="Descrizione")

    due_date = models.DateField(verbose_name="Data scadenza")

    status = models.CharField(
        max_length=20,
        choices=DeadlineStatus.choices,
        default=DeadlineStatus.PENDING,
        verbose_name="Stato",
    )

    # Completamento
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Completata il")
    completed_by_contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_deadlines',
        verbose_name="Completata da",
    )

    # Materiale ricevuto dal cliente e gia' visionato dall'operatore: usato
    # per l'avviso "materiali ricevuti" sul cruscotto (sparisce quando
    # l'operatore apre il dettaglio). Un nuovo upload (completed_at piu'
    # recente) lo fa ricomparire.
    materials_reviewed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Materiale visionato il")

    # Reminder tracking
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_count = models.IntegerField(default=0, verbose_name="N. reminder inviati")

    notes = models.TextField(blank=True, verbose_name="Note")

    # --- Servizi compilabili dal cliente (snapshot dal DeadlineTemplate) ---
    submission_kind = models.CharField(
        max_length=20, default='file', verbose_name="Tipo consegna",
    )
    content_schema = models.JSONField(
        default=list, blank=True, verbose_name="Campi richiesti",
        help_text="Definizione dei campi che il cliente deve compilare.",
    )
    content_data = models.JSONField(
        default=dict, blank=True, verbose_name="Dati inviati dal cliente",
    )

    class Meta:
        verbose_name = "Scadenza"
        verbose_name_plural = "Scadenze"
        ordering = ['due_date']
        indexes = [
            models.Index(fields=['due_date']),
            models.Index(fields=['status', 'due_date']),
        ]

    @property
    def portal_title(self):
        """Titolo mostrato al cliente nel portale. Lato admin resta 'title'."""
        if self.status == DeadlineStatus.RECEIVED:
            return {
                'pagamento_acconto': 'Acconto regolarizzato',
                'pagamento_saldo': 'Saldo regolarizzato',
            }.get(self.deadline_type, self.title)
        return {
            'pagamento_saldo': 'Saldo da pagare',
            'pagamento_acconto': 'Acconto da pagare',
        }.get(self.deadline_type, self.title)

    def __str__(self):
        return f"{self.title} · {self.due_date}"

    @property
    def is_overdue(self):
        return (
            self.status in [DeadlineStatus.PENDING, DeadlineStatus.REMINDER_SENT]
            and self.due_date < timezone.now().date()
        )

    @property
    def days_until_due(self):
        """Giorni mancanti alla scadenza (negativo se in ritardo)."""
        return (self.due_date - timezone.now().date()).days

    @property
    def days_remaining(self):
        """Giorni mancanti o di ritardo, sempre positivo (per i template)."""
        return abs((self.due_date - timezone.now().date()).days)

    def mark_as_received(self, contact=None):
        """Marca come ricevuta."""
        self.status = DeadlineStatus.RECEIVED
        self.completed_at = timezone.now()
        self.completed_by_contact = contact
        self.save(update_fields=[
            'status', 'completed_at', 'completed_by_contact', 'updated_at'
        ])


# Re-export dei modelli ecommerce per renderli scopribili da Django
from contracts.payments import (  # noqa: E402
    Payment,
    PaymentMethodChoice,
    PaymentStatus,
    CartSession,
    CartSessionStatus,
)
