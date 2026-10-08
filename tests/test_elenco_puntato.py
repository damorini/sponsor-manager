"""Descrizioni scritte come elenco («· voce· voce» o una voce per riga col
trattino): elenco puntato nel preventivo, nel portale e nella Domanda."""
from django.template import Context, Template

from core.elenco import voci_elenco

SIES = ('· Area nuda· Appendimento in Expo Room · Live on stage (1 sessione di 30 '
        'minuti)· Logo su sito e stampa · Newsletter congressuale')


def test_voci_da_pallini_su_una_riga():
    assert voci_elenco(SIES) == [
        'Area nuda', 'Appendimento in Expo Room', 'Live on stage (1 sessione di 30 minuti)',
        'Logo su sito e stampa', 'Newsletter congressuale']


def test_voci_una_per_riga():
    assert voci_elenco('· Open Space\n· Display in the Expo Room \n· Live on stage') == [
        'Open Space', 'Display in the Expo Room', 'Live on stage']
    assert voci_elenco('- uno\n- due') == ['uno', 'due']


def test_testo_normale_non_e_elenco():
    assert voci_elenco("Iscrizione standard. L'iscrizione include l'accesso.") is None
    assert voci_elenco('Riga uno\nRiga due') is None
    assert voci_elenco('') is None


def test_filtro():
    t = Template('{% load elenco %}{{ d|elenco_puntato }}')
    html = t.render(Context({'d': SIES + ' <b>'}))
    assert html.count('<li>') == 5 and '<ul class="elenco"' in html
    assert '&lt;b&gt;' in html
    assert t.render(Context({'d': 'Riga uno\nRiga due'})) == 'Riga uno<br>Riga due'
