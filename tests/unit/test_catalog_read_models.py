# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from cps.catalog import read_models
from cps.external_books.models import ExternalBook
from cps.movie_library.models import Movie


@pytest.fixture
def fake_urls(monkeypatch):
    def url_for(endpoint, **values):
        item_id = values.get("book_id", values.get("movie_id"))
        return f"/{endpoint}/{item_id}"
    monkeypatch.setattr(read_models, "url_for", url_for)


@pytest.mark.unit
def test_adapters_keep_identical_numeric_ids_in_source_specific_urls(fake_urls):
    calibre = SimpleNamespace(
        id=7, title="Calibre copy", authors=[SimpleNamespace(name="Author")],
        timestamp=datetime(2026, 1, 1),
    )
    external = ExternalBook(id=7, title="Kindle copy", media_type="kindle", location="Kindle",
                            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    external.authors = ["Author"]
    movie = Movie(id=7, title="Movie", media_format="DVD", director="Director",
                  release_date="2016-11-11", created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
                  is_watched=True)

    calibre_result = read_models.calibre_card(calibre)
    external_result = read_models.external_book_card(external)
    movie_result = read_models.movie_card(movie)

    assert calibre_result.detail_url == "/web.show_book/7"
    assert external_result.detail_url == "/external_books.detail/7"
    assert movie_result.detail_url == "/movies.detail/7"
    assert external_result.badge == "Kindle"
    assert movie_result.byline == "Director · 2016"
    assert movie_result.state == "Watched"
