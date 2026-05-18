"""
Admin per Users.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, UserRole


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'full_name_display', 'role_badge', 'is_active', 'last_login')
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('email', 'first_name', 'last_name', 'username')
    ordering = ('email',)
    
    fieldsets = (
        (None, {
            'fields': ('email', 'username', 'password'),
        }),
        ('Informazioni personali', {
            'fields': ('first_name', 'last_name', 'role'),
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
