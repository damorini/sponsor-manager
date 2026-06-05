"""
End-to-end del cambio lingua IT/EN del portale.

Wiring (config/urls.py + config/settings/base.py):
  - LocaleMiddleware + LANGUAGES=[it,en] + LOCALE_PATHS=locale/
  - endpoint Django set_language a /i18n/setlang/
  - selettore lingua nella pagina di login (portal/auth/login.html)
  - catalogo tradotto in locale/en/LC_MESSAGES/django.po (compilato in .mo)

Verifica: la pagina di login rende in IT di default e passa a EN dopo set_language.
"""
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestLanguageSwitch:
    def test_login_default_italian(self, client):
        """Default IT: la login mostra le stringhe italiane."""
        resp = client.get(reverse('portal:login'))
        content = resp.content.decode()
        assert resp.status_code == 200
        assert 'Accedi' in content
        assert 'Log in' not in content

    def test_switch_to_english(self, client):
        """Dopo set_language=en la login rende in inglese."""
        resp = client.post(
            reverse('set_language'),
            {'language': 'en', 'next': reverse('portal:login')},
            follow=True,
        )
        content = resp.content.decode()
        assert resp.status_code == 200
        assert 'Sponsor portal login' in content  # "Accesso portale sponsor"
        assert 'Log in' in content                 # "Accedi"
        assert 'Accedi' not in content

    def test_switch_back_to_italian(self, client):
        """Tornare a IT ripristina le stringhe italiane."""
        client.post(
            reverse('set_language'),
            {'language': 'en', 'next': reverse('portal:login')},
            follow=True,
        )
        resp = client.post(
            reverse('set_language'),
            {'language': 'it', 'next': reverse('portal:login')},
            follow=True,
        )
        content = resp.content.decode()
        assert 'Accedi' in content
        assert 'Log in' not in content
