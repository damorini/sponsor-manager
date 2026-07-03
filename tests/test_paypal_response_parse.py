"""Regressione: l'SDK PayPal restituisce la risposta come oggetto tipizzato
(.body -> Order) e come JSON grezzo (.text). _response_to_dict deve produrre un
dict semplice (usando .text), altrimenti create/capture crashano con
AttributeError: 'Order' object has no attribute 'get'."""
from contracts.services.paypal_service import _response_to_dict


class _FakeApiResponse:
    def __init__(self, text, body=None):
        self.text = text
        self.body = body if body is not None else object()  # oggetto tipizzato


def test_usa_text_json_grezzo():
    r = _FakeApiResponse('{"id": "ORD123", "links": [{"rel": "approve", "href": "http://pay"}]}')
    d = _response_to_dict(r)
    assert d['id'] == 'ORD123'
    assert d['links'][0]['rel'] == 'approve'
    assert d['links'][0]['href'] == 'http://pay'


def test_fallback_body_dict():
    class R:
        text = None
        body = {'id': 'ORD9', 'status': 'CREATED'}
    d = _response_to_dict(R())
    assert d['id'] == 'ORD9'
    assert d['status'] == 'CREATED'


def test_body_stringa_json():
    class R:
        text = ''
        body = '{"id": "ORD5"}'
    assert _response_to_dict(R())['id'] == 'ORD5'
