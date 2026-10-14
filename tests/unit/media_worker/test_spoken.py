import pytest

from app.media_worker.spoken import normalize_spoken


@pytest.mark.parametrize("language,text,expected", [
    ("pt", "cento e vinte", "120"),
    ("pt", "um dois zero", "120"),
    ("pt", "cem", "100"),
    ("pt", "duzentos e cinquenta", "250"),
    ("pt", "trezentos e cinco", "305"),
    ("pt", "cento e vinte e oito", "128"),
    ("pt", "noventa e nove", "99"),
    ("pt", "dezessete", "17"),
    ("pt", "minha glicose está em cento e vinte e oito miligramas por decilitro", "minha glicose está em 128 mg/dL"),
    ("pt", "cinco vírgula seis milimoles por litro", "5.6 mmol/L"),
    ("en", "one hundred and twenty", "120"),
    ("en", "one hundred twenty", "120"),
    ("en", "a hundred and five", "105"),
    ("en", "one two zero", "120"),
    ("en", "one oh five", "105"),
    ("en", "ninety eight", "98"),
    ("en", "my glucose is one hundred twenty eight milligrams per deciliter", "my glucose is 128 mg/dL"),
    ("en", "five point six millimoles per liter", "5.6 mmol/L"),
    ("es", "ciento veinte", "120"),
    ("es", "uno dos cero", "120"),
    ("es", "ciento veintiocho miligramos por decilitro", "128 mg/dL"),
    ("es", "doscientos cincuenta y uno", "251"),
    ("es", "noventa y ocho", "98"),
    ("es", "cinco coma seis milimoles por litro", "5.6 mmol/L"),
    ("es", "La lectura fue de 90 y 5 mg/dL.", "La lectura fue de 95 mg/dL."),
    ("pt", "deu 100 e 20 mg/dL", "deu 120 mg/dL"),
    ("en", "it was 90 and 5 mg per deciliter", "it was 95 mg/dL"),
    ("pt", "128 mg/dL", "128 mg/dL"),
    ("pt", "deu 120 e 140", "deu 120 e 140"),
    ("pt", "medi hoje de manhã", "medi hoje de manhã"),
])
def test_spoken_numbers_and_units_become_digits(language, text, expected):
    assert normalize_spoken(text, language) == expected


def test_unknown_language_picks_the_lexicon_that_matches():
    assert normalize_spoken("cento e vinte miligramas por decilitro") == "120 mg/dL"
    assert normalize_spoken("one hundred twenty") == "120"
    assert normalize_spoken("ciento veinte") == "120"


def test_a_plain_article_or_connector_is_not_turned_into_a_number():
    assert normalize_spoken("um dia e uma noite", "pt") == "um dia e uma noite"
    assert normalize_spoken("uma glicose de cento e vinte", "pt") == "uma glicose de 120"
    assert normalize_spoken("una medición de ciento diez", "es") == "una medición de 110"
    assert normalize_spoken("glicose normal", "pt") == "glicose normal"
