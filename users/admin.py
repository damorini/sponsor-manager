"""
Admin per Users.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, UserRole

from django.contrib.auth.forms import AdminPasswordChangeForm


class ItAdminPasswordChangeForm(AdminPasswordChangeForm):
    """Traduce in italiano la voce 'Password-based authentication' (novita' Django 5.1)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        f = self.fields.get('usable_password')
        if f is not None:
            f.label = "Autenticazione tramite password"
            f.help_text = (
                "Se la imposti su «Disabilitata», l'utente non potra' piu' accedere con una "
                "password. In teoria potrebbe ancora entrare con altri sistemi (es. accesso "
                "unico SSO o LDAP) se fossero configurati: in questo gestionale pero' c'e' solo "
                "l'accesso con password, quindi disabilitandola l'utente non potra' piu' entrare "
                "finche' non la riabiliti e gli imposti una nuova password."
            )
            scelte = [("true", "Abilitata"), ("false", "Disabilitata")]
            f.choices = scelte
            try:
                f.widget.choices = scelte
            except Exception:
                pass


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('cognome_display', 'nome_display', 'email', 'role_badge', 'is_active', 'last_login')
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('email', 'first_name', 'last_name', 'username')
    ordering = ('last_name', 'first_name', 'email')
    filter_horizontal = ('managed_events', 'groups', 'user_permissions')
    change_password_form = ItAdminPasswordChangeForm
    
    fieldsets = (
        (None, {
            'fields': ('email', 'username', 'password'),
        }),
        ('Informazioni personali', {
            'fields': ('first_name', 'last_name', 'role'),
        }),
        ('Eventi gestiti', {
            'fields': ('managed_events',),
            'description': "Operatori e Sola lettura vedranno solo contratti, "
                           "scadenze, pagamenti, eventi e stand di questi eventi. "
                           "Amministratori e superuser vedono tutto.",
        }),
        ('Permessi', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',),
        }),
        ('Date importanti', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',),
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'first_name', 'last_name',
                       'role', 'password1', 'password2'),
        }),
    )

    @admin.display(description='Nome', ordering='first_name')
    def nome_display(self, obj):
        return obj.first_name or '—'

    @admin.display(description='Cognome', ordering='last_name')
    def cognome_display(self, obj):
        return obj.last_name or '—'

    @admin.display(description='Nome completo', ordering='last_name')
    def full_name_display(self, obj):
        return obj.get_full_name() or '—'

    @admin.display(description='Ruolo')
    def role_badge(self, obj):
        from django.utils.html import format_html
        colors = {
            UserRole.ADMIN: '#ba2121',
            UserRole.OPERATOR: '#79aec8',
            UserRole.READONLY: '#999',
            UserRole.SPONSOR: '#41ad7c',
        }
        color = colors.get(obj.role, '#666')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_role_display()
        )
