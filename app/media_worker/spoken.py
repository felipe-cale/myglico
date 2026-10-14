"""Deterministic spoken-number and unit normalization for ASR transcripts (pt, en, es).

"cento e vinte", "um dois zero", "one hundred and twenty", "ciento veinte" all become 120, and
"miligramas por decilitro" / "mg per deciliter" become "mg/dL". Digits already present are left
untouched. Anything that does not parse cleanly is left as the speaker said it, so the strict
digit-and-unit gate downstream stays the only thing that can create a reading.
"""

from __future__ import annotations

import re
import unicodedata

_DIGITS = {
    "pt": {"zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
           "seis": 6, "sete": 7, "oito": 8, "nove": 9},
    "en": {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
           "seven": 7, "eight": 8, "nine": 9},
    "es": {"cero": 0, "uno": 1, "un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
           "seis": 6, "siete": 7, "ocho": 8, "nueve": 9},
}

_TEENS = {  # 10-19, plus es 21-29 which are single words
    "pt": {"dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14, "quinze": 15,
           "dezesseis": 16, "dezasseis": 16, "dezessete": 17, "dezassete": 17, "dezoito": 18,
           "dezenove": 19, "dezanove": 19},
    "en": {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
           "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19},
    "es": {"diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
           "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
           "veintiuno": 21, "veintiun": 21, "veintiuna": 21, "veintidos": 22, "veintitres": 23,
           "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26, "veintisiete": 27,
           "veintiocho": 28, "veintinueve": 29},
}

_TENS = {
    "pt": {"vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70,
           "oitenta": 80, "noventa": 90},
    "en": {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
           "eighty": 80, "ninety": 90},
    "es": {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70,
           "ochenta": 80, "noventa": 90},
}

_HUNDREDS = {  # pt/es have dedicated words; en is "<digit> hundred"
    "pt": {"cem": 100, "cento": 100, "duzentos": 200, "duzentas": 200, "trezentos": 300, "trezentas": 300,
           "quatrocentos": 400, "quatrocentas": 400, "quinhentos": 500, "quinhentas": 500,
           "seiscentos": 600, "seiscentas": 600, "setecentos": 700, "setecentas": 700,
           "oitocentos": 800, "oitocentas": 800, "novecentos": 900, "novecentas": 900},
    "en": {},
    "es": {"cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200, "trescientos": 300,
           "trescientas": 300, "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500,
           "quinientas": 500, "seiscientos": 600, "seiscientas": 600, "setecientos": 700,
           "setecientas": 700, "ochocientos": 800, "ochocientas": 800, "novecientos": 900,
           "novecientas": 900},
}

# Standing alone these are articles ("uma glicose"), not the number 1.
_ARTICLES = {"pt": {"um", "uma"}, "en": set(), "es": {"un", "una"}}

_AND = {"pt": {"e"}, "en": {"and"}, "es": {"y"}}
_POINT = {"pt": {"virgula", "ponto"}, "en": {"point", "dot"}, "es": {"coma", "punto"}}

_MG_DL = re.compile(
    r"\b(?:miligramas?|milligrams?|miligramos?|mg)\s*(?:por|per|/)\s*(?:decilitros?|deciliters?|decilitres?|dl)\b",
    re.I)
_MMOL_L = re.compile(
    r"\b(?:milimol(?:es)?|millimol(?:es)?|mmol)\s*(?:por|per|/)\s*(?:litros?|liters?|litres?|l)\b", re.I)


def _fold(word: str) -> str:
    word = unicodedata.normalize("NFKD", word.lower())
    return "".join(ch for ch in word if not unicodedata.combining(ch))


def _unit(lang: str, tokens: list[str], i: int) -> tuple[int, int] | None:
    token = tokens[i] if i < len(tokens) else ""
    if token in _DIGITS[lang] and token != "oh":
        return _DIGITS[lang][token], i + 1
    return None


def _below_hundred(lang: str, tokens: list[str], i: int) -> tuple[int, int] | None:
    if i >= len(tokens):
        return None
    token = tokens[i]
    if token in _TEENS[lang]:
        return _TEENS[lang][token], i + 1
    if token in _TENS[lang]:
        value = _TENS[lang][token]
        j = i + 1
        if lang == "en":
            nxt = _unit(lang, tokens, j)
            if nxt and nxt[0] > 0:
                return value + nxt[0], nxt[1]
        elif j < len(tokens) and tokens[j] in _AND[lang]:
            nxt = _unit(lang, tokens, j + 1)
            if nxt and nxt[0] > 0:
                return value + nxt[0], nxt[1]
        return value, j
    unit = _unit(lang, tokens, i)
    if unit:
        return unit
    return None


def _cardinal(lang: str, tokens: list[str], i: int) -> tuple[int, int] | None:
    if i >= len(tokens):
        return None
    total, j = 0, i
    hundred = None
    if lang == "en":
        if tokens[j] == "a" and j + 1 < len(tokens) and tokens[j + 1] == "hundred":
            hundred, j = 100, j + 2
        else:
            unit = _unit(lang, tokens, j)
            if unit and unit[0] > 0 and unit[1] < len(tokens) and tokens[unit[1]] == "hundred":
                hundred, j = unit[0] * 100, unit[1] + 1
    elif tokens[j] in _HUNDREDS[lang]:
        hundred, j = _HUNDREDS[lang][tokens[j]], j + 1
    if hundred is not None:
        total = hundred
        k = j + 1 if j < len(tokens) and tokens[j] in _AND[lang] else j
        rest = _below_hundred(lang, tokens, k)
        if rest and rest[0] > 0:
            return total + rest[0], rest[1]
        return total, j
    return _below_hundred(lang, tokens, i)


def _convert(lang: str, words: list[str]) -> tuple[list[str], int]:
    tokens = [_fold(w.strip(".,;:!?¿¡")) for w in words]
    out: list[str] = []
    changed = 0
    i = 0
    while i < len(words):
        # A run of two or more single digit words is read digit by digit ("um dois zero").
        j = i
        run = []
        while j < len(tokens) and tokens[j] in _DIGITS[lang]:
            run.append(str(_DIGITS[lang][tokens[j]]))
            j += 1
        if len(run) >= 2:
            out.append("".join(run))
            changed += 1
            i = j
            continue
        number = _cardinal(lang, tokens, i)
        if number is None:
            out.append(words[i])
            i += 1
            continue
        value, j = number
        if j == i + 1 and tokens[i] in _ARTICLES[lang]:
            out.append(words[i])
            i += 1
            continue
        text = str(value)
        # Decimals: "cinco vírgula seis" -> 5.6
        if j < len(tokens) and tokens[j] in _POINT[lang]:
            frac, k = [], j + 1
            while k < len(tokens) and tokens[k] in _DIGITS[lang] and len(frac) < 2:
                frac.append(str(_DIGITS[lang][tokens[k]]))
                k += 1
            if frac:
                text, j = f"{value}.{''.join(frac)}", k
        out.append(text)
        changed += 1
        i = j
    return out, changed


def normalize_spoken(text: str, language: str | None = None) -> str:
    """Return the transcript with spoken numbers and units rewritten as digits and mg/dL, mmol/L."""
    words = text.split()
    if not words:
        return text
    lang = (language or "")[:2]
    candidates = [lang] if lang in _DIGITS else list(_DIGITS)
    best, best_changed = words, 0
    for code in candidates:
        converted, changed = _convert(code, words)
        if changed > best_changed:
            best, best_changed = converted, changed
    result = " ".join(best)
    result = _MG_DL.sub("mg/dL", result)
    return _MMOL_L.sub("mmol/L", result)
