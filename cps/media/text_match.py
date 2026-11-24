# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared, dependency-free text and identifier matching helpers."""

import re
import unicodedata

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "is",
    "of", "on", "or", "the", "to", "with",
}

PRINTING_WORDS = {
    "anniversary", "annotated", "collector", "collectors", "deluxe", "edition",
    "expanded", "illustrated", "international", "large", "new", "print", "revised",
    "special", "unabridged", "updated",
}

DERIVATIVE_WORDS = {
    "abridged", "adaptation", "analysis", "dramatized", "graphic", "guide",
    "novel", "study", "summary", "workbook",
}

BUNDLE_WORDS = {
    "anthology", "box", "collection", "complete", "megapack", "omnibus", "set",
    "trilogy",
}

_AUTHOR_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}

_SERIES_LABEL = re.compile(r"^\s*(?P<label>[^:]{1,40}?)\s+\d+(?:\.\d+)?\s*:\s*(?=\S)")
_BRACKETED = re.compile(r"[(\[][^)\]]*[)\]]")
_ALTERNATE_TITLE = re.compile(r",\s*or\s+.*$", re.IGNORECASE)
_TOKEN = re.compile(r"[a-z0-9]+")


def normalize_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


def tokens(value):
    return _TOKEN.findall(normalize_text(value))


def significant_tokens(value):
    return [token for token in tokens(value) if token not in STOPWORDS]


def normalize_title(value):
    return " ".join(significant_tokens(value))


def author_surname(value):
    parts = tokens(value)
    while parts and parts[-1] in _AUTHOR_SUFFIXES:
        parts.pop()
    return parts[-1] if parts else ""


def normalize_isbn(value):
    return re.sub(r"[^0-9X]", "", str(value or "").upper())


def isbn10_to_13(isbn10):
    if len(isbn10) != 10 or not isbn10[:9].isdigit():
        return None
    base = "978" + isbn10[:9]
    total = sum((1 if index % 2 == 0 else 3) * int(digit) for index, digit in enumerate(base))
    return base + str((10 - total % 10) % 10)


def isbn13_to_10(isbn13):
    if len(isbn13) != 13 or not isbn13.startswith("978") or not isbn13[3:12].isdigit():
        return None
    base = isbn13[3:12]
    total = sum((10 - index) * int(digit) for index, digit in enumerate(base))
    check = (11 - total % 11) % 11
    return base + ("X" if check == 10 else str(check))


def isbn_variants(value):
    isbn = normalize_isbn(value)
    if len(isbn) == 10:
        return frozenset(item for item in (isbn, isbn10_to_13(isbn)) if item)
    if len(isbn) == 13:
        return frozenset(item for item in (isbn, isbn13_to_10(isbn)) if item)
    return frozenset()


def strip_series_label(title, has_series):
    if has_series:
        match = _SERIES_LABEL.match(str(title or ""))
        if match:
            return str(title)[match.end():]
    return str(title or "")


def strip_numbered_parentheticals(title):
    return _BRACKETED.sub(lambda match: " " if re.search(r"\d", match.group(0)) else match.group(0), str(title or ""))


def strip_alternate_title(title):
    return _ALTERNATE_TITLE.sub("", str(title or ""))


def clean_title_tokens(title, has_series=False):
    value = strip_series_label(title, has_series)
    value = strip_numbered_parentheticals(value)
    value = strip_alternate_title(value)
    return frozenset(significant_tokens(value))


def is_printing_word(token):
    return token in PRINTING_WORDS


def is_derivative_word(token):
    return token in DERIVATIVE_WORDS


def is_bundle_word(token):
    return token in BUNDLE_WORDS
