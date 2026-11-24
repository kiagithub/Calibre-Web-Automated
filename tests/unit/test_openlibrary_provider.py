# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from cps.metadata_provider import openlibrary


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


@pytest.mark.unit
def test_openlibrary_parses_search_results(monkeypatch):
    payload = {
        "docs": [
            {
                "key": "/works/OL123W",
                "title": "Dune",
                "author_name": ["Frank Herbert"],
                "first_publish_year": 1965,
                "isbn": ["9780441172719", "0441172717"],
                "cover_i": 12345,
                "language": ["eng"],
                "publisher": ["Chilton"],
                "subject": ["Science fiction", "Desert"],
                "series": ["Dune Chronicles"],
                "ratings_average": 4.3,
            }
        ]
    }
    monkeypatch.setattr(openlibrary.requests, "get", lambda *args, **kwargs: FakeResponse(payload))

    results = openlibrary.OpenLibrary().search("Dune", "generic.svg", "en")

    assert len(results) == 1
    result = results[0]
    assert result.title == "Dune"
    assert result.id == "OL123W"
    assert result.authors == ["Frank Herbert"]
    assert result.cover == "https://covers.openlibrary.org/b/id/12345-L.jpg"
    assert result.publishedDate == "1965"
    assert result.publisher == "Chilton"
    assert result.series == "Dune Chronicles"
    assert result.identifiers["openlibrary"] == "OL123W"
    assert result.identifiers["isbn"] == "9780441172719"
    assert result.identifiers["isbn_10"] == "0441172717"
    assert result.languages == ["English"]
    assert "Science fiction" in result.tags


@pytest.mark.unit
def test_openlibrary_search_failure_returns_empty_results(monkeypatch):
    def fail(*args, **kwargs):
        raise openlibrary.requests.RequestException("offline")

    monkeypatch.setattr(openlibrary.requests, "get", fail)

    assert openlibrary.OpenLibrary().search("Dune") == []


@pytest.mark.unit
def test_openlibrary_supports_search_by(monkeypatch):
    captured_params = []

    def fake_get(url, params=None, **kwargs):
        captured_params.append(params)
        return FakeResponse({"docs": []})

    monkeypatch.setattr(openlibrary.requests, "get", fake_get)
    provider = openlibrary.OpenLibrary()

    provider.search("Frank Herbert", search_by="author")
    assert captured_params[-1]["author"] == "Frank Herbert"
    assert "q" not in captured_params[-1]

    provider.search("Dune", search_by="title")
    assert captured_params[-1]["title"] == "Dune"
    assert "q" not in captured_params[-1]

    provider.search("9780441172719", search_by="isbn")
    assert captured_params[-1]["isbn"] == "9780441172719"
    assert "q" not in captured_params[-1]

    provider.search("Dune", search_by="all")
    assert captured_params[-1]["q"] == "Dune"
