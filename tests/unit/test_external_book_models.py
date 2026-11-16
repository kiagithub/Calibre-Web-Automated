# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from cps import ub
from cps.external_books.models import ExternalBook, ExternalBookTag, normalize_tag_name
from cps.movie_library.models import Movie


@pytest.fixture
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ub.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


@pytest.mark.unit
class TestExternalBookModels:
    def test_string_arrays_are_normalized_and_malformed_json_is_safe(self, db_session):
        book = ExternalBook(title="Arrival", media_type="kindle")
        book.authors = [" Ted Chiang ", "", 42, "Another Author"]
        book.languages = ["en", " en ".strip()]
        assert book.authors == ["Ted Chiang", "Another Author"]
        assert book.languages == ["en", "en"]

        book.authors_json = "not-json"
        book.languages_json = '{"not": "a list"}'
        assert book.authors == []
        assert book.languages == []

    def test_duplicate_isbn_and_provider_ids_allow_separate_copies(self, db_session):
        db_session.add_all([
            ExternalBook(title="Arrival", media_type="physical", isbn_13="9781101972120",
                         metadata_provider="google", metadata_id="same-work", location="Upstairs"),
            ExternalBook(title="Arrival", media_type="kindle", isbn_13="9781101972120",
                         metadata_provider="google", metadata_id="same-work", location="Kindle"),
        ])
        db_session.commit()
        assert db_session.query(ExternalBook).count() == 2

    def test_tags_normalize_deduplicate_and_cascade(self, db_session):
        book = ExternalBook(title="Arrival", media_type="physical")
        book.tags = [
            ExternalBookTag(name=" Science   Fiction ", normalized_name=normalize_tag_name(" Science   Fiction ")),
            ExternalBookTag(name="Owned", normalized_name=normalize_tag_name("Owned")),
        ]
        db_session.add(book)
        db_session.commit()
        assert book.tag_names == ["Owned", "Science Fiction"]
        assert book.tags[1].normalized_name == "science fiction"

        db_session.delete(book)
        db_session.commit()
        assert db_session.query(ExternalBookTag).count() == 0

    def test_duplicate_normalized_tag_is_rejected(self, db_session):
        book = ExternalBook(title="Arrival", media_type="physical")
        book.tags = [
            ExternalBookTag(name="Owned", normalized_name="owned"),
            ExternalBookTag(name="owned", normalized_name="owned"),
        ]
        db_session.add(book)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_external_book_migration_adds_audiobook_columns(self, tmp_path):
        engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'app.db'}")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE external_book (id INTEGER PRIMARY KEY, title VARCHAR(300), "
                "media_type VARCHAR(20))"
            )

        ub.migrate_external_book_table(engine, None)
        ub.migrate_external_book_table(engine, None)

        with engine.connect() as connection:
            columns = {
                row[1] for row in connection.exec_driver_sql("PRAGMA table_info(external_book)")
            }
        assert {"narrator", "duration_minutes", "abridged", "audio_format"} <= columns
        engine.dispose()

    def test_create_all_adds_tables_to_existing_app_database(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Movie.__table__.create(engine)
        assert "external_book" not in inspect(engine).get_table_names()

        ub.Base.metadata.create_all(engine)
        assert {"external_book", "external_book_tag"} <= set(inspect(engine).get_table_names())
        engine.dispose()
