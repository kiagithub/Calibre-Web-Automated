# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from io import BytesIO

import pytest
from flask import Flask, g, jsonify
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cps import db, ub, usermanagement
from cps.external_books import covers, routes, thumbnails
from cps.external_books.models import ExternalBook
from cps.jinjia import jinjia
from cps.media import ImageDownloadError
from cps.search_metadata import meta
from cps.wishlist import notifications as wishlist_notifications
from cps.wishlist.models import MediaRequest

JPEG = b"\xff\xd8\xff" + b"test-image"


class FakeUser:
    id = 1
    is_authenticated = True
    is_anonymous = False
    locale = "en"
    name = "Test user"
    kindle_mail = ""

    def __init__(self, edit=True, admin=False, delete=True):
        self.edit = edit
        self.admin = admin
        self.delete = delete

    def role_upload(self):
        return False

    def role_edit(self):
        return self.edit

    def role_admin(self):
        return self.admin

    def role_delete_books(self):
        return self.delete


@pytest.fixture
def external_app(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS calibre")
    ub.Base.metadata.create_all(engine)
    db.Base.metadata.create_all(engine)
    db_session = sessionmaker(bind=engine)()
    calibre_session = sessionmaker(bind=engine)()
    monkeypatch.setattr(ub, "session", db_session)
    monkeypatch.setattr(ub, "app_DB_path", str(tmp_path / "app.db"))
    monkeypatch.setattr(covers, "cover_limit", lambda: 8 * 1024 * 1024)
    monkeypatch.setattr(routes, "render_title_template", lambda template, **context: jsonify(
        template=template,
        entries=[entry.title for entry in context.get("entries", [])],
        total=context.get("total"),
        errors=context.get("errors", []),
    ))

    app = Flask("cps")
    app.config.update(SECRET_KEY="test", TESTING=True)
    app.register_blueprint(routes.external_books)
    app.register_blueprint(meta)
    app.register_blueprint(jinjia)
    user = FakeUser()
    app.config["TEST_USER"] = user

    @app.before_request
    def authenticate():
        g.flask_httpauth_user = app.config["TEST_USER"]

    monkeypatch.setattr(usermanagement.config, "config_allow_reverse_proxy_header_login", False, raising=False)
    monkeypatch.setattr(usermanagement.config, "config_anonbrowse", 0, raising=False)
    yield app, db_session, calibre_session, user, tmp_path
    db_session.close()
    calibre_session.close()
    engine.dispose()


def form_data(**overrides):
    data = {
        "title": "Arrival",
        "authors": "Ted Chiang",
        "media_type": "physical",
        "tags": "Owned, Science Fiction",
        "location": "Shelf A",
        "condition": "Good",
        "personal_rating": "8",
        "notes": "Signed copy",
        "isbn_13": "9781101972120",
    }
    data.update(overrides)
    return data


@pytest.mark.unit
class TestExternalBookRoutes:
    def test_create_filter_edit_and_delete_without_calibre_side_effects(self, external_app):
        app, session, calibre_session, _user, _tmp_path = external_app
        calibre_counts = {table: calibre_session.query(table).count() for table in (db.Books, db.Data)}
        client = app.test_client()
        response = client.post("/books/personal/new", data=form_data())
        assert response.status_code == 302
        book = session.query(ExternalBook).one()
        assert book.media_type == "physical"
        assert book.authors == ["Ted Chiang"]
        assert book.tag_names == ["Owned", "Science Fiction"]
        assert {table: calibre_session.query(table).count() for table in calibre_counts} == calibre_counts

        assert client.get("/books/personal/?q=Arrival").get_json()["entries"] == ["Arrival"]
        assert client.get("/books/personal/?q=Missing").get_json()["entries"] == []
        assert client.get("/books/personal/?media_type=kindle").get_json()["entries"] == []
        assert client.get("/books/personal/?tag=owned").get_json()["entries"] == ["Arrival"]

        response = client.post(f"/books/personal/{book.id}/edit", data=form_data(
            title="Arrival — updated", media_type="kindle", tags="Favorites",
            location="Kindle", condition="", metadata_provider="google", metadata_id="abc",
            metadata_selected="1",
        ))
        assert response.status_code == 302
        assert book.title == "Arrival — updated"
        assert book.media_type == "kindle"
        assert book.location == "Kindle"
        assert book.notes == "Signed copy"
        assert book.tag_names == ["Favorites"]
        assert book.metadata_updated_at is not None

        response = client.post(f"/books/personal/{book.id}/delete")
        assert response.status_code == 302
        assert session.query(ExternalBook).count() == 0

    def test_invalid_type_does_not_create_book(self, external_app):
        app, session, _calibre, _user, _tmp_path = external_app
        response = app.test_client().post("/books/personal/new", data=form_data(media_type="ebook"))
        assert response.status_code == 400
        assert session.query(ExternalBook).count() == 0

    def test_duplicate_isbn_is_allowed(self, external_app):
        app, session, _calibre, _user, _tmp_path = external_app
        client = app.test_client()
        assert client.post("/books/personal/new", data=form_data()).status_code == 302
        assert client.post("/books/personal/new", data=form_data(media_type="kindle")).status_code == 302
        assert session.query(ExternalBook).count() == 2

    def test_uploaded_cover_is_served_replaced_and_deleted(self, external_app):
        app, session, _calibre, _user, tmp_path = external_app
        client = app.test_client()
        response = client.post("/books/personal/new", data=form_data(
            cover=(BytesIO(JPEG), "cover.jpg")
        ), content_type="multipart/form-data")
        assert response.status_code == 302
        book = session.query(ExternalBook).one()
        first_filename = book.cover_filename
        first_path = tmp_path / "external_book_covers" / first_filename
        assert first_path.is_file()
        assert client.get(f"/books/personal/{book.id}/cover").data == JPEG

        response = client.post(f"/books/personal/{book.id}/edit", data=form_data(
            cover=(BytesIO(JPEG + b"new"), "cover.jpg")
        ), content_type="multipart/form-data")
        assert response.status_code == 302
        assert book.cover_filename != first_filename
        assert not first_path.exists()
        assert (tmp_path / "external_book_covers" / book.cover_filename).is_file()

        assert client.post(f"/books/personal/{book.id}/delete").status_code == 302
        assert not (tmp_path / "external_book_covers" / book.cover_filename).exists()

    def test_remote_cover_failure_still_saves_metadata(self, external_app, monkeypatch):
        app, session, _calibre, _user, _tmp_path = external_app
        def fail_download(_url, _max_bytes=None):
            raise ImageDownloadError("Unavailable")
        monkeypatch.setattr(routes, "remote_cover", fail_download)
        response = app.test_client().post("/books/personal/new", data=form_data(
            cover_url="https://books.google.com/cover.jpg", metadata_selected="1"
        ))
        assert response.status_code == 302
        book = session.query(ExternalBook).one()
        assert book.cover_filename == ""

    def test_metadata_cover_serves_and_caches_small_thumbnail(self, external_app, monkeypatch):
        app, _session, _calibre, _user, _tmp_path = external_app
        calls = []

        def fake_download(url):
            calls.append(url)
            return JPEG, "jpg"

        thumbnails.clear_thumbnail_cache()
        monkeypatch.setattr(thumbnails, "WandImage", None)
        monkeypatch.setattr(thumbnails, "download_cover", fake_download)

        client = app.test_client()
        url = "https://example.test/cover.jpg"
        first = client.get("/books/personal/metadata/cover", query_string={"url": url})
        second = client.get("/books/personal/metadata/cover", query_string={"url": url})

        assert first.status_code == 200
        assert first.data == JPEG
        assert first.mimetype == "image/jpeg"
        assert first.headers["Cache-Control"] == "private, max-age=86400"
        assert second.data == JPEG
        assert calls == [url]
        thumbnails.clear_thumbnail_cache()

    def test_metadata_cover_rejects_invalid_url_and_requires_edit_permission(
        self, external_app, monkeypatch
    ):
        app, _session, _calibre, user, _tmp_path = external_app
        client = app.test_client()

        assert client.get(
            "/books/personal/metadata/cover", query_string={"url": "javascript:alert(1)"}
        ).status_code == 400

        user.edit = False
        assert client.get(
            "/books/personal/metadata/cover", query_string={"url": "https://example.test/cover.jpg"}
        ).status_code == 403

    def test_metadata_cover_falls_back_to_generic_cover_on_download_error(
        self, external_app, monkeypatch
    ):
        app, _session, _calibre, _user, _tmp_path = external_app

        def fail_download(_url):
            raise ImageDownloadError("Unavailable")

        thumbnails.clear_thumbnail_cache()
        monkeypatch.setattr(thumbnails, "download_cover", fail_download)

        response = app.test_client().get(
            "/books/personal/metadata/cover", query_string={"url": "https://example.test/cover.jpg"}
        )

        assert response.status_code == 200
        assert b"<svg" in response.data
        thumbnails.clear_thumbnail_cache()

    def test_fulfilling_wishlist_request_links_new_book(self, external_app, monkeypatch):
        app, session, _calibre, _user, _tmp_path = external_app
        monkeypatch.setattr(wishlist_notifications, "notify_request", lambda *args, **kwargs: None)
        entry = MediaRequest(user_id=1, content_type="book", status="pending", title="Dune")
        entry.authors = ["Frank Herbert"]
        entry.identifiers = {"isbn_13": "9780441172719"}
        session.add(entry)
        session.commit()

        response = app.test_client().post(
            "/books/personal/new", data=form_data(title="Dune", request_id=str(entry.id))
        )

        assert response.status_code == 302
        book = session.query(ExternalBook).one()
        assert entry.status == "fulfilled"
        assert entry.fulfilled_external_book_id == book.id

    def test_edit_and_delete_permissions_are_enforced(self, external_app):
        app, session, _calibre, user, _tmp_path = external_app
        user.edit = False
        assert app.test_client().post("/books/personal/new", data=form_data()).status_code == 403
        user.edit = True
        assert app.test_client().post("/books/personal/new", data=form_data()).status_code == 302
        user.delete = False
        book = session.query(ExternalBook).one()
        assert app.test_client().post(f"/books/personal/{book.id}/delete").status_code == 403
