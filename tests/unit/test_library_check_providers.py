# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cps import ub
from cps.external_books.models import ExternalBook
from cps.media.library_check import providers
from cps.media.text_match import isbn_variants
from cps.movie_library.models import Movie


@pytest.fixture
def media_session(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    ub.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(ub, "session", session)
    app_db = tmp_path / "app.db"
    app_db.touch()
    monkeypatch.setattr(ub, "app_DB_path", str(app_db))
    yield session
    session.close()
    engine.dispose()


@pytest.mark.unit
def test_personal_entries_index_identifiers_and_media_type(media_session):
    book = ExternalBook(title="Dune", media_type="physical", isbn_13="9780441172719")
    book.authors = ["Frank Herbert"]
    book.series = "Dune Chronicles"
    book.metadata_provider = "openlibrary"
    book.metadata_id = "OL123W"
    media_session.add(book)
    media_session.commit()

    entries = providers.personal_entries()

    assert len(entries) == 1
    assert entries[0].kind == "personal"
    assert entries[0].title_tokens == frozenset({"dune"})
    assert entries[0].author_tokens == frozenset({"herbert"})
    assert entries[0].isbns == isbn_variants("9780441172719")
    assert entries[0].external_ids == frozenset({("openlibrary", "OL123W")})


@pytest.mark.unit
def test_movie_entries_include_tmdb_and_year(media_session):
    media_session.add(
        Movie(
            title="Arrival",
            original_title="Arrival",
            media_format="Blu-ray",
            release_date="2016-11-11",
            tmdb_id=329865,
            imdb_id="tt2543164",
        )
    )
    media_session.commit()

    entries = providers.movie_entries()

    assert len(entries) == 1
    assert entries[0].tmdb_id == 329865
    assert entries[0].imdb_id == "TT2543164"
    assert entries[0].year == "2016"
    assert entries[0].title_tokens == frozenset({"arrival"})
