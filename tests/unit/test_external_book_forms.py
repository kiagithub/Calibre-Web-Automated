# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from cps.external_books.forms import apply_values, parse_tags, validate_form
from cps.external_books.models import ExternalBook


def valid_form(**overrides):
    form = {
        "title": "Arrival",
        "authors": "Ted Chiang & Another Author",
        "languages": "en, fr",
        "media_type": "physical",
        "tags": "Owned, Science Fiction, owned",
        "isbn_13": "978-1-101-97212-0",
        "isbn_10": "1101972123",
        "asin": "B00P7J0Y3A",
        "published_date": "2016-11-11",
        "date_acquired": "2026-01-02",
        "page_count": "304",
        "personal_rating": "8",
        "metadata_url": "https://books.google.com/books?id=example",
        "cover_url": "https://books.google.com/example.jpg",
    }
    form.update(overrides)
    return form


@pytest.mark.unit
class TestExternalBookForms:
    def test_valid_form_normalizes_metadata_and_collections(self):
        values, errors = validate_form(valid_form())
        assert errors == []
        assert values["authors"] == ["Ted Chiang", "Another Author"]
        assert values["languages"] == ["en", "fr"]
        assert values["tags"] == ["Owned", "Science Fiction"]
        assert values["isbn_13"] == "9781101972120"
        assert values["isbn_10"] == "1101972123"
        assert values["page_count"] == 304
        assert values["personal_rating"] == 8

    @pytest.mark.parametrize("overrides,message", [
        ({"title": ""}, "Title is required"),
        ({"media_type": "audiobook"}, "Select Physical"),
        ({"condition": "Broken"}, "valid condition"),
        ({"published_date": "2026-02-31"}, "valid date"),
        ({"published_date": "11/11/2016"}, "YYYY"),
        ({"date_acquired": "tomorrow"}, "valid date"),
        ({"page_count": "0"}, "between 1"),
        ({"personal_rating": "11"}, "between 0 and 10"),
        ({"isbn_10": "bad"}, "ISBN-10"),
        ({"isbn_13": "123"}, "ISBN-13"),
        ({"asin": "bad!"}, "ASIN"),
        ({"metadata_url": "file:///etc/passwd"}, "HTTP or HTTPS"),
        ({"cover_url": "https://user:secret@example.com/cover.jpg"}, "HTTP or HTTPS"),
    ])
    def test_invalid_fields_are_rejected(self, overrides, message):
        _values, errors = validate_form(valid_form(**overrides))
        assert any(message in error for error in errors), errors

    def test_tags_are_unicode_normalized_trimmed_and_deduplicated(self):
        errors = []
        assert parse_tags(" Ｓｃｉｅｎｃｅ   Fiction , science fiction, , Owned ", errors) == [
            "Science Fiction", "Owned"
        ]
        assert errors == []

    def test_provider_description_is_converted_to_safe_plain_text(self):
        values, errors = validate_form(valid_form(
            description="<p>Hello <strong>world</strong>.</p><script>alert(1)</script><style>body{}</style>"
        ))
        assert errors == []
        assert values["description"] == "Hello world."

    def test_apply_values_separates_metadata_from_owned_fields(self):
        book = ExternalBook(title="Old", media_type="kindle", location="Original")
        values, errors = validate_form(valid_form(
            title="New title", media_type="kindle", location="Kindle library",
            tags="Favorites", metadata_selected="1", metadata_provider="google", metadata_id="abc",
        ))
        assert errors == []
        apply_values(book, values)
        assert book.title == "New title"
        assert book.location == "Kindle library"
        assert book.tag_names == ["Favorites"]
        assert book.authors == ["Ted Chiang", "Another Author"]
        assert book.metadata_updated_at is not None
