# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from cps.metadata_merge import dedupe_records


def record(provider, provider_id, title, authors=(), isbn="", cover="", description=""):
    identifiers = {"isbn": isbn} if isbn else {}
    return {
        "id": provider_id,
        "title": title,
        "authors": list(authors),
        "identifiers": identifiers,
        "source": {"id": provider},
        "cover": cover,
        "description": description,
        "publisher": "",
        "publishedDate": "",
        "series": "",
        "series_index": 0,
        "languages": [],
        "tags": [],
    }


@pytest.mark.unit
def test_records_with_the_same_isbn_are_merged():
    records = [
        record("google", "1", "Dune", ["Frank Herbert"], isbn="9780441172719"),
        record("openlibrary", "OL1W", "Dune (Deluxe)", ["Frank Herbert"], isbn="0-441-17271-7"),
    ]

    merged = dedupe_records(records)

    assert len(merged) == 1
    assert merged[0]["source"]["id"] == "google"


@pytest.mark.unit
def test_records_with_the_same_provider_id_are_merged():
    records = [
        record("hardcover", "42", "Dune", ["Frank Herbert"]),
        record("hardcover", "42", "Dune Messiah", ["Frank Herbert"]),
    ]

    assert len(dedupe_records(records)) == 1


@pytest.mark.unit
def test_records_with_the_same_title_and_author_are_merged():
    records = [
        record("google", "1", "Dune", ["Frank Herbert"]),
        record("openlibrary", "OL1W", "Dune", ["Frank Herbert"]),
    ]

    assert len(dedupe_records(records)) == 1


@pytest.mark.unit
def test_different_books_are_not_merged():
    records = [
        record("google", "1", "Dune", ["Frank Herbert"]),
        record("google", "2", "Hyperion", ["Dan Simmons"]),
    ]

    assert len(dedupe_records(records)) == 2


@pytest.mark.unit
def test_merge_fills_missing_description_cover_and_identifiers():
    records = [
        record("google", "1", "Dune", ["Frank Herbert"], description="Short"),
        record(
            "openlibrary",
            "OL1W",
            "Dune",
            ["Frank Herbert"],
            isbn="9780441172719",
            cover="https://covers.example/dune.jpg",
            description="A much longer description of Dune.",
        ),
    ]

    merged = dedupe_records(records)[0]

    assert merged["description"] == "A much longer description of Dune."
    assert merged["cover"] == "https://covers.example/dune.jpg"
    assert merged["identifiers"]["isbn"] == "9780441172719"
