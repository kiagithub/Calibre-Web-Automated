# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cps import db, ub
from cps.catalog import service
from cps.catalog.read_models import CatalogCard
from cps.external_books.models import ExternalBook, ExternalBookTag
from cps.movie_library.models import Movie


def card(source, item):
    return CatalogCard(
        source=source,
        id=item.id,
        title=item.title,
        byline="",
        cover_url=f"/{source}/{item.id}/cover",
        detail_url=f"/{source}/{item.id}",
        badge=source,
        location="",
    )


@pytest.fixture
def catalog_db(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS calibre")
    db.Base.metadata.create_all(engine)
    ub.Base.metadata.create_all(engine)
    calibre_session = sessionmaker(bind=engine)()
    app_session = sessionmaker(bind=engine)()
    fake_calibre = SimpleNamespace(session=calibre_session, common_filters=lambda: True)
    monkeypatch.setattr(service, "calibre_db", fake_calibre)
    monkeypatch.setattr(ub, "session", app_session)
    monkeypatch.setattr(service, "calibre_card", lambda book: card("calibre", book))
    monkeypatch.setattr(service, "external_book_card", lambda book: card("external", book))
    monkeypatch.setattr(service, "movie_card", lambda movie: card("movie", movie))
    yield calibre_session, app_session, fake_calibre
    calibre_session.close()
    app_session.close()
    engine.dispose()


def add_calibre(session, title, timestamp, tags=None):
    book = db.Books(
        title=title, sort=title, author_sort="Author", timestamp=timestamp, pubdate=timestamp,
        series_index="1.0", last_modified=timestamp, path=title, has_cover=0,
        authors=[], tags=[], languages=[],
    )
    book.authors = [db.Authors("Author " + title, "Author " + title)]
    book.tags = [db.Tags(name) for name in tags or []]
    session.add(book)
    return book


def add_external(session, title, timestamp, media_type="physical", tags=None):
    book = ExternalBook(title=title, media_type=media_type, created_at=timestamp)
    book.authors = ["Author"]
    book.tags = [ExternalBookTag(name=name) for name in tags or []]
    session.add(book)
    return book


@pytest.mark.unit
class TestCombinedCatalog:
    def test_keyset_pages_merge_sources_without_collisions_or_omissions(self, catalog_db):
        calibre_session, app_session, _ = catalog_db
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for index in range(5):
            add_calibre(calibre_session, f"Calibre {index}", start + timedelta(days=index * 2))
            add_external(app_session, f"External {index}", start + timedelta(days=index * 2 + 1))
        calibre_session.commit()
        app_session.commit()

        first = service.combined_books(per_page=4)
        second = service.combined_books(cursor=first.next_cursor, per_page=4)
        third = service.combined_books(cursor=second.next_cursor, per_page=4)

        assert first.total == second.total == third.total == 10
        assert first.has_next and not first.has_prev
        assert second.has_prev and second.has_next
        assert third.has_prev and not third.has_next
        assert [len(result.cards) for result in (first, second, third)] == [4, 4, 2]
        keys = [(card.source, card.id) for result in (first, second, third) for card in result.cards]
        assert len(keys) == len(set(keys)) == 10
        assert ("calibre", 1) in keys and ("external", 1) in keys
        assert first.cards[0].title == "External 4"

    def test_previous_cursor_returns_the_prior_page(self, catalog_db):
        calibre_session, app_session, _ = catalog_db
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for index in range(4):
            add_external(app_session, f"External {index}", start + timedelta(days=index))
        app_session.commit()

        first = service.combined_books(per_page=2)
        second = service.combined_books(cursor=first.next_cursor, per_page=2)
        back = service.combined_books(
            cursor=second.prev_cursor, direction="prev", per_page=2
        )

        assert [(card.source, card.id) for card in back.cards] == [
            (card.source, card.id) for card in first.cards
        ]
        assert back.has_prev is False
        assert back.has_next is True

    def test_previous_cursor_handles_equal_timestamps_across_sources(self, catalog_db):
        calibre_session, app_session, _ = catalog_db
        when = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for index in range(2):
            add_calibre(calibre_session, f"Calibre {index}", when)
            add_external(app_session, f"External {index}", when)
        calibre_session.commit()
        app_session.commit()

        first = service.combined_books(per_page=2)
        second = service.combined_books(cursor=first.next_cursor, per_page=2)
        back = service.combined_books(
            cursor=second.prev_cursor, direction="prev", per_page=2
        )

        assert [card.title for card in first.cards] == ["External 1", "External 0"]
        assert [card.title for card in second.cards] == ["Calibre 1", "Calibre 0"]
        assert [card.title for card in back.cards] == [card.title for card in first.cards]

    def test_invalid_cursor_starts_at_the_first_page(self, catalog_db):
        calibre_session, app_session, _ = catalog_db
        add_calibre(calibre_session, "Only", datetime(2026, 1, 1))
        calibre_session.commit()
        result = service.combined_books(cursor="not-a-cursor", per_page=24)
        assert result.total == 1
        assert result.has_prev is False
        assert result.has_next is False
        assert result.cards[0].title == "Only"

    def test_filters_apply_to_equivalent_sources(self, catalog_db):
        calibre_session, app_session, _ = catalog_db
        add_calibre(calibre_session, "Shared title", datetime(2026, 1, 1), tags=["Favorites"])
        add_calibre(calibre_session, "Other", datetime(2026, 1, 2))
        add_external(app_session, "Shared title", datetime(2026, 1, 3), media_type="kindle", tags=["Favorites"])
        add_external(app_session, "Other", datetime(2026, 1, 4), media_type="physical", tags=["Owned"])
        calibre_session.commit()
        app_session.commit()

        assert service.combined_books(query_text="Shared").total == 2
        assert service.combined_books(media_type="kindle").total == 1
        assert service.combined_books(tag="favorites").total == 2
        assert service.combined_books(source="calibre").total == 2
        assert service.combined_books(source="external").total == 2
        assert service.combined_books(source="calibre", media_type="kindle").total == 0

    def test_calibre_visibility_filter_is_applied_to_count_and_rows(self, catalog_db):
        calibre_session, app_session, fake_calibre = catalog_db
        visible = add_calibre(calibre_session, "Visible", datetime(2026, 1, 1))
        hidden = add_calibre(calibre_session, "Hidden", datetime(2026, 1, 2))
        calibre_session.commit()
        fake_calibre.common_filters = lambda: db.Books.id != hidden.id

        result = service.combined_books()
        assert result.total == 1
        assert [(card.source, card.id) for card in result.cards] == [("calibre", visible.id)]

    def test_available_tags_include_visible_calibre_and_external_tags(self, catalog_db):
        calibre_session, app_session, fake_calibre = catalog_db
        add_calibre(calibre_session, "Visible", datetime(2026, 1, 1), tags=["Shared"])
        hidden = add_calibre(calibre_session, "Hidden", datetime(2026, 1, 2), tags=["Secret"])
        add_external(app_session, "External", datetime(2026, 1, 3), tags=["Owned", "shared"])
        calibre_session.commit()
        app_session.commit()
        fake_calibre.common_filters = lambda: db.Books.id != hidden.id

        tags = service.available_tags()
        assert [tag.casefold() for tag in tags] == ["owned", "shared"]
        assert "Secret" not in tags

    def test_recent_home_returns_books_movies_and_counts(self, catalog_db):
        calibre_session, app_session, _ = catalog_db
        add_external(app_session, "Book", datetime(2026, 1, 1))
        app_session.add(Movie(title="Movie", media_format="DVD", created_at=datetime(2026, 1, 2)))
        app_session.commit()

        books, movies, book_count, movie_count = service.recent_home()
        assert [item.title for item in books] == ["Book"]
        assert [item.title for item in movies] == ["Movie"]
        assert book_count == movie_count == 1
