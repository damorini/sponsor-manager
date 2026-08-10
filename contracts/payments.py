"""
Modelli per ecommerce: Payment e CartSession.

Payment registra i pagamenti ricevuti (PayPal o bonifico) per i contratti
addon. NON sostituisce InvoiceExport: la fattura la emette comunque il
sistema esterno di fatturazione.

CartSession traccia il "carrello" attivo dello sponsor. Il carrello vero
è un Contract con kind=ADDON e status=DRAFT; questa tabella aggiunge solo
metadati di sessione.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class PaymentMethodChoice(models.TextChoices):
    PAYPAL = 'paypal', 'PayPal'
    BANK_TRANSFER = 'bank_transfer', 'Bonifico'
    MANUAL = 'manual', 'Manuale'


class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'In attesa'
    PROCESSING = 'processing', 'In elaborazione'
    SUCCEEDED = 'succeeded', 'Completato'
    FAILED = 'failed', 'Fallito'
    REFUNDED = 'refunded', 'Rimborsato'
    PARTIAL_REFUND = 'partial_refund', 'Rimborso parziale'


class Payment(TimeStampedModel):
    """
    Pagamento registrato per un contratto.
    
    Per PayPal: viene creato all'avvio del checkout (status=pending),
    aggiornato a 'succeeded' dal webhook handler quando PayPal conferma.
    
    Per bonifico: viene creato dal sistema con status=pending al checkout
    (mostra IBAN e causale al cliente), poi un operatore conferma manualmente
    quando l'accredito arriva sul conto (passa a 'succeeded').
    """
    contract = models.ForeignKey(
        'contracts.Contract',
        on_delete=models.PROTECT,
        related_name='payments',
        verbose_name="Contratto",
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethodChoice.choices,
        verbose_name="Metodo",
    )

    amount_gross = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Importo lordo",
        help_text="Totale pagato dal cliente",
    )
    amount_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Commissione",
        help_text="Commissione PayPal o costi bonifico",
    )
    # amount_net è GENERATED nel DB; in Django property
    currency = models.CharField(
        max_length=3,
        default='EUR',
        verbose_name="Valuta",
    )

    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        verbose_name="Stato",
    )

    # Riferimenti PayPal
    paypal_order_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="PayPal order ID",
    )
    paypal_capture_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="PayPal capture ID",
    )
    paypal_payer_email = models.EmailField(blank=True)
    paypal_payer_id = models.CharField(max_length=100, blank=True)
    paypal_response = models.JSONField(
        null=True,
        blank=True,
        verbose_name="PayPal raw response",
    )

    # Riferimenti bonifico
    bank_transfer_reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Causale bonifico",
        help_text="Univoca, generata dall'app",
    )
    bank_transfer_received_at = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data accredito",
    )
    bank_transfer_confirmed_by_user = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmed_payments',
        verbose_name="Confermato da",
    )

    # Timestamp
    initiated_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Avviato il",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)

    # Idempotency: ID dell'ultimo evento webhook PayPal processato
    last_webhook_event_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Ultimo webhook ID",
        help_text="Per idempotenza dei webhook PayPal",
    )

    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamenti"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['paypal_order_id']),
            models.Index(fields=['bank_transfer_reference']),
        ]

    def __str__(self):
        return f"{self.get_payment_method_display()} · {self.amount_gross}€ · {self.get_status_display()}"

    @property
    def amount_net(self):
        """Netto incassato (lordo - commissioni)."""
        return self.amount_gross - self.amount_fee

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.status == PaymentStatus.SUCCEEDED and self.contract_id:
            try:
                self.contract.reconcile_payment_deadlines()
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "Riconciliazione scadenze pagamento fallita per payment %s", self.id)

    def mark_succeeded(self, completed_at=None, paypal_capture_id=None):
        """
        Marca pagamento come completato e firma il contratto associato.
        Idempotente: se già succeeded, non fa nulla.
        """
        if self.status == PaymentStatus.SUCCEEDED:
            return

        self.status = PaymentStatus.SUCCEEDED
        self.completed_at = completed_at or timezone.now()
        if paypal_capture_id:
            self.paypal_capture_id = paypal_capture_id
        self.save()

        # Firma il contratto associato
        self.contract.mark_payment_succeeded()

        # Email di conferma pagamento (sincrona in dev con EAGER=True).
        try:
            from contracts.tasks.notifications import send_payment_confirmation_notification
            send_payment_confirmation_notification.delay(self.id)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Invio conferma pagamento fallito per payment %s", self.id
            )

    def mark_failed(self, reason=''):
        """Marca pagamento come fallito.

        MAI degradare un pagamento gia' riuscito: nel race return-URL vs
        webhook il secondo arrivato riceveva ORDER_ALREADY_CAPTURED da PayPal
        e sovrascriveva SUCCEEDED con FAILED - il cliente aveva pagato ma il
        sistema tornava a chiedere l'importo (rischio doppio pagamento).
        Ricontrolla lo stato dal DB per vedere anche il commit concorrente."""
        stato_db = type(self).objects.filter(pk=self.pk).values_list(
            'status', flat=True).first()
        if stato_db == PaymentStatus.SUCCEEDED or self.status == PaymentStatus.SUCCEEDED:
            import logging
            logging.getLogger(__name__).warning(
                "mark_failed ignorato su payment %s gia' SUCCEEDED (reason: %s)",
                self.id, reason)
            return
        self.status = PaymentStatus.FAILED
        self.failed_at = timezone.now()
        self.failure_reason = reason
        self.save()


class CartSessionStatus(models.TextChoices):
    ACTIVE = 'active', 'Attivo'
    ABANDONED = 'abandoned', 'Abbandonato'
    COMPLETED = 'completed', 'Completato'
    EXPIRED = 'expired', 'Scaduto'


class CartSession(TimeStampedModel):
    """
    Sessione carrello dello sponsor nel portale ecommerce.
    
    Il carrello vero è un Contract bozza con kind=ADDON; questa tabella
    aggiunge metadati di sessione (ultima attività, abbandono, recupero).
    """
    contract = models.OneToOneField(
        'contracts.Contract',
        on_delete=models.CASCADE,
        related_name='cart_session',
        verbose_name="Contratto bozza (carrello)",
    )
    contact = models.ForeignKey(
        'sponsors.Contact',
        on_delete=models.CASCADE,
        related_name='cart_sessions',
        verbose_name="Contatto",
    )

    status = models.CharField(
        max_length=20,
        choices=CartSessionStatus.choices,
        default=CartSessionStatus.ACTIVE,
        verbose_name="Stato",
    )

    last_activity_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Ultima attività",
    )
    abandoned_email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Email abbandono inviata",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Sessione carrello"
        verbose_name_plural = "Sessioni carrello"
        ordering = ['-last_activity_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['last_activity_at']),
        ]

    def __str__(self):
        return f"Carrello {self.contact.full_name} · {self.get_status_display()}"

    def touch(self):
        """Aggiorna last_activity_at. Chiamato a ogni interazione carrello."""
        self.last_activity_at = timezone.now()
        self.save(update_fields=['last_activity_at', 'updated_at'])

    def mark_abandoned(self):
        if self.status == CartSessionStatus.ACTIVE:
            self.status = CartSessionStatus.ABANDONED
            self.save(update_fields=['status', 'updated_at'])

    def mark_completed(self):
        self.status = CartSessionStatus.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])
