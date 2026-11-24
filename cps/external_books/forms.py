# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

from .models import AUDIO_FORMATS, CONDITIONS, MEDIA_TYPES, ExternalBookTag, clean_tag_name, normalize_tag_name

TEXT_FIELDS = {
    "title": 300,
    "description": 20000,
    "publisher": 300,
    "published_date": 10,
    "series": 300,
    "series_index": 20,
    "media_type": 20,
    "narrator": 300,
    "audio_format": 20,
    "binding": 40,
    "edition": 200,
    "location": 200,
    "condition": 40,
    "date_acquired": 10,
    "notes": 10000,
    "isbn_10": 20,
    "isbn_13": 20,
    "asin": 20,
    "metadata_provider": 50,
    "metadata_id": 255,
    "metadata_url": 1000,
}
ARRAY_FIELDS = {"authors": 5000, "languages": 500}


class _PlainTextParser(HTMLParser):
    BLOCKS = {"br", "div", "li", "p", "section", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, _attrs):
        if tag in ("script", "style"):
            self.ignored_depth += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.ignored_depth:
            self.ignored_depth -= 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.ignored_depth:
            self.parts.append(data)


def plain_text(value):
    parser = _PlainTextParser()
    parser.feed(value or "")
    parser.close()
    text = "".join(parser.parts)
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def _text(form, field, limit, errors):
    value = str(form.get(field, "") or "").strip()
    if len(value) > limit:
        errors.append(f"{field.replace('_', ' ').title()} must be {limit} characters or fewer.")
    return value


def _integer(form, field, label, minimum, maximum, errors):
    value = str(form.get(field, "") or "").strip()
    if not value:
        return None
    try:
        number = int(value)
        if not minimum <= number <= maximum:
            raise ValueError
        return number
    except (TypeError, ValueError):
        errors.append(f"{label} must be between {minimum} and {maximum}.")
        return None


def _publication_date(value, errors):
    if not value:
        return ""
    if not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value):
        errors.append("Publication date must use YYYY, YYYY-MM, or YYYY-MM-DD.")
        return value
    try:
        if len(value) == 4:
            date(int(value), 1, 1)
        elif len(value) == 7:
            date(int(value[:4]), int(value[5:]), 1)
        else:
            date.fromisoformat(value)
    except ValueError:
        errors.append("Publication date must be a valid date.")
    return value


def _acquired_date(value, errors):
    if not value:
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        errors.append("Date acquired must be a valid date.")
        return value


def _string_array(value, field, limit, errors, separator):
    raw = str(value or "").strip()
    if len(raw) > limit:
        errors.append(f"{field.title()} must be {limit} characters or fewer.")
    items = []
    seen = set()
    for item in re.split(separator, raw):
        item = " ".join(item.split())
        if not item:
            continue
        if len(item) > 200:
            errors.append(f"Each {field[:-1]} must be 200 characters or fewer.")
            continue
        folded = item.casefold()
        if folded not in seen:
            items.append(item)
            seen.add(folded)
    if len(items) > 50:
        errors.append(f"Use no more than 50 {field}.")
    return items[:50]


def parse_tags(value, errors):
    raw = str(value or "").strip()
    if len(raw) > 5000:
        errors.append("Tags must be 5000 characters or fewer.")
    tags = []
    seen = set()
    for item in raw.split(","):
        name = clean_tag_name(item)
        if not name:
            continue
        normalized = normalize_tag_name(name)
        if len(name) > 100 or len(normalized) > 100:
            errors.append("Each tag must be 100 characters or fewer.")
            continue
        if normalized not in seen:
            tags.append(name)
            seen.add(normalized)
    if len(tags) > 50:
        errors.append("Use no more than 50 tags per book.")
    return tags[:50]


def _identifier(value, pattern, label, errors):
    value = re.sub(r"[\s-]", "", value or "").upper()
    if value and not re.fullmatch(pattern, value):
        errors.append(f"Enter a valid {label}.")
    return value


def _metadata_url(value, errors):
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        errors.append("Metadata source must be a valid HTTP or HTTPS URL.")
    return value


def validate_form(form):
    errors = []
    values = {field: _text(form, field, limit, errors) for field, limit in TEXT_FIELDS.items()}
    values["description"] = plain_text(values["description"])
    if not values["title"]:
        errors.append("Title is required.")
    if values["media_type"] not in MEDIA_TYPES:
        errors.append("Select Physical, Kindle, Other digital, or Audiobook as the book type.")
    if values["condition"] and values["condition"] not in CONDITIONS:
        errors.append("Select a valid condition.")
    if values["audio_format"] and values["audio_format"] not in AUDIO_FORMATS:
        errors.append("Select a valid audiobook format.")

    values["published_date"] = _publication_date(values["published_date"], errors)
    values["date_acquired"] = _acquired_date(values["date_acquired"], errors)
    values["page_count"] = _integer(form, "page_count", "Page count", 1, 50000, errors)
    values["duration_minutes"] = _integer(
        form, "duration_minutes", "Audiobook duration", 1, 100000, errors
    )
    values["personal_rating"] = _integer(form, "personal_rating", "Personal rating", 0, 10, errors)
    values["abridged"] = form.get("abridged") == "on"
    values["authors"] = _string_array(form.get("authors"), "authors", ARRAY_FIELDS["authors"], errors, r"[&\n]+")
    values["languages"] = _string_array(form.get("languages"), "languages", ARRAY_FIELDS["languages"], errors, r"[,\n]+")
    values["tags"] = parse_tags(form.get("tags"), errors)

    values["isbn_10"] = _identifier(values["isbn_10"], r"(?:\d{9}[\dX])", "ISBN-10", errors)
    values["isbn_13"] = _identifier(values["isbn_13"], r"\d{13}", "ISBN-13", errors)
    values["asin"] = _identifier(values["asin"], r"[A-Z0-9]{10,20}", "ASIN", errors)
    values["metadata_url"] = _metadata_url(values["metadata_url"], errors)
    values["cover_url"] = _metadata_url(_text(form, "cover_url", 2000, errors), errors)
    values["metadata_selected"] = form.get("metadata_selected") == "1"
    values["remove_cover"] = form.get("remove_cover") == "on"
    return values, errors


def apply_values(book, values):
    for field in TEXT_FIELDS:
        setattr(book, field, values[field])
    for field in ("page_count", "duration_minutes", "personal_rating", "abridged"):
        setattr(book, field, values[field])
    book.authors = values["authors"]
    book.languages = values["languages"]
    desired_tags = {normalize_tag_name(name): name for name in values["tags"]}
    for tag in list(book.tags):
        name = desired_tags.pop(tag.normalized_name, None)
        if name is None:
            book.tags.remove(tag)
        elif tag.name != name:
            tag.name = name
    for name in desired_tags.values():
        book.tags.append(ExternalBookTag(name=name))
    if values["metadata_selected"]:
        book.metadata_updated_at = datetime.now(timezone.utc)
    book.updated_at = datetime.now(timezone.utc)
