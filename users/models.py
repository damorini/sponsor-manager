"""
Utente del backoffice (team interno).

Estende AbstractUser di Django: mantiene tutta l'auth built-in (password,
sessioni, permission system) e aggiunge il campo `role` per distinguere
admin / operatori / sola lettura.
"""
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    ADMIN = 'admin', 'Amministratore'
    OPERATOR = 'operator', 'Operatore'
    READONLY = 'readonly', 'Sola lettura'
    SPONSOR = 'sponsor', 'Sponsor (portale)'


class User(AbstractUser):
    """
    Utente del backoffice.
    
    Usa email come identificatore principale (più naturale dello username
    per un sistema interno aziendale).
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    email = models.EmailField(
        unique=True,
        verbose_name="Email",
    )
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.OPERATOR,
        verbose_name="Ruolo",
    )

    # Email come campo di login al posto di username
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']  # username resta richiesto da AbstractUser

    class Meta:
        verbose_name = "Utente"
        verbose_name_plural = "Utenti"
        ordering = ['email']

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def is_admin(self):
        return self.role == UserRole.ADMIN

    @property
    def is_operator(self):
        return self.role == UserRole.OPERATOR

    @property
    def is_readonly(self):
        return self.role == UserRole.READONLY

    @property
    def is_sponsor(self):
        """Utente del portale sponsor (non del backoffice interno)."""
        return self.role == UserRole.SPONSOR

    @property
    def is_internal_user(self):
        """Vero per admin/operator/readonly, false per sponsor."""
        return self.role in [UserRole.ADMIN, UserRole.OPERATOR, UserRole.READONLY]
