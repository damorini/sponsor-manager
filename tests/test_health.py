"""Healthcheck endpoint usato da Docker/nginx."""
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_ok(client):
    resp = client.get(reverse('health'))
    assert resp.status_code == 200
    assert resp.json()['status'] == 'ok'
