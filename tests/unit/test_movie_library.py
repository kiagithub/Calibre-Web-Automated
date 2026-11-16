# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from cps import ub, usermanagement
from cps.jinjia import jinjia
from cps.movie_library import metadata, routes
from cps.movie_library.metadata import MovieMetadataError, TMDBClient, image_type
from cps.movie_library.models import MOVIE_CREATED_AT_INDEX, Movie, ensure_movie_indexes
from flask import Flask, g, jsonify, render_template
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

JPEG = b"\xff\xd8\xff" + b"test-image"


class FakeResponse:
    def __init__(self, payload=None, data=b"", status=200):
        self.payload = payload
        self.data = data
        self.status_code = status
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise metadata.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload

    def iter_content(self, size):
        for index in range(0, len(self.data), size):
            yield self.data[index:index + size]

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, *responses):
        self.headers = {}
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected network request")
        return self.responses.pop(0)


@pytest.mark.unit
def test_movie_created_at_index_is_added_to_existing_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE movie (id INTEGER PRIMARY KEY, created_at DATETIME)"
        )

    ensure_movie_indexes(engine)
    ensure_movie_indexes(engine)

    with engine.connect() as connection:
        indexes = {
            row[1] for row in connection.exec_driver_sql("PRAGMA index_list('movie')")
        }
    assert MOVIE_CREATED_AT_INDEX in indexes
    engine.dispose()


@pytest.mark.unit
class TestTMDBMetadata:
    def test_unconfigured_client_does_not_make_network_request(self):
        http = FakeSession()
        client = TMDBClient(api_key="", read_access_token="", session=http)
        with pytest.raises(MovieMetadataError, match="not configured"):
            client.search("Arrival")
        assert http.calls == []

    def test_example_placeholders_do_not_enable_network_requests(self):
        http = FakeSession()
        client = TMDBClient(
            api_key="your_tmdb_api_key_here",
            read_access_token="your_tmdb_read_access_token_here",
            session=http,
        )
        assert not client.configured
        with pytest.raises(MovieMetadataError, match="not configured"):
            client.search("Arrival")
        assert http.calls == []

    def test_search_normalizes_results_and_uses_api_key(self):
        http = FakeSession(FakeResponse({"results": [{
            "id": 329865,
            "title": "Arrival",
            "original_title": "Arrival",
            "release_date": "2016-11-11",
            "overview": "A linguist works with the military.",
            "poster_path": "/poster.jpg",
            "vote_average": 7.61,
        }]}))
        results = TMDBClient(api_key="secret", read_access_token="", session=http).search("Arrival", 2016)
        assert results[0]["tmdb_id"] == 329865
        assert results[0]["year"] == "2016"
        assert results[0]["tmdb_rating"] == 7.6
        assert results[0]["poster_url"].endswith("/poster.jpg")
        assert http.calls[0][1]["params"]["api_key"] == "secret"
        assert http.calls[0][1]["params"]["year"] == 2016
        assert http.calls[0][1]["params"]["include_adult"] == "false"

    def test_read_access_token_uses_bearer_header(self):
        http = FakeSession(FakeResponse({"results": []}))
        TMDBClient(api_key="", read_access_token="token", session=http).search("Arrival")
        assert http.calls[0][1]["headers"]["Authorization"] == "Bearer token"
        assert "api_key" not in http.calls[0][1]["params"]

    def test_details_extract_credits_genres_and_us_certification(self):
        payload = {
            "id": 329865, "title": "Arrival", "release_date": "2016-11-11",
            "overview": "Overview", "runtime": 116, "imdb_id": "tt2543164",
            "vote_average": 7.6, "poster_path": "/poster.jpg",
            "credits": {
                "crew": [{"name": "Denis Villeneuve", "job": "Director"}, {"name": "Someone", "job": "Producer"}],
                "cast": [{"name": "Amy Adams"}, {"name": "Jeremy Renner"}],
            },
            "genres": [{"name": "Drama"}, {"name": "Science Fiction"}],
            "release_dates": {"results": [{"iso_3166_1": "US", "release_dates": [
                {"type": 2, "certification": ""}, {"type": 3, "certification": "PG-13"},
            ]}]},
        }
        result = TMDBClient(api_key="key", read_access_token="", session=FakeSession(FakeResponse(payload))).details(329865)
        assert result["director"] == "Denis Villeneuve"
        assert result["cast_members"] == "Amy Adams, Jeremy Renner"
        assert result["genres"] == "Drama, Science Fiction"
        assert result["runtime"] == 116
        assert result["content_rating"] == "PG-13"

    def test_malformed_json_has_safe_error(self):
        response = FakeResponse(ValueError("bad json"))
        client = TMDBClient(api_key="key", read_access_token="", session=FakeSession(response))
        with pytest.raises(MovieMetadataError, match="could not complete"):
            client.search("Arrival")

    def test_poster_only_allows_tmdb_https_host(self):
        client = TMDBClient(api_key="key", read_access_token="", session=FakeSession())
        with pytest.raises(MovieMetadataError, match="trusted TMDB"):
            client.download_poster("https://example.com/t/p/w500/poster.jpg")

    def test_poster_does_not_follow_redirects(self):
        response = FakeResponse(data=JPEG, status=302)
        client = TMDBClient(api_key="key", read_access_token="", session=FakeSession(response))
        with pytest.raises(MovieMetadataError, match="redirects"):
            client.download_poster("https://image.tmdb.org/t/p/w500/poster.jpg")
        assert response.closed
        assert client.http.calls[0][1]["allow_redirects"] is False

    def test_poster_validates_image_and_closes_response(self):
        response = FakeResponse(data=JPEG)
        client = TMDBClient(api_key="key", read_access_token="", session=FakeSession(response))
        data, extension = client.download_poster("https://image.tmdb.org/t/p/w500/poster.jpg")
        assert (data, extension) == (JPEG, "jpg")
        assert response.closed

    def test_poster_rejects_oversized_response(self):
        response = FakeResponse(data=b"x" * (metadata.MAX_POSTER_BYTES + 1))
        client = TMDBClient(api_key="key", read_access_token="", session=FakeSession(response))
        with pytest.raises(MovieMetadataError, match="size limit"):
            client.download_poster("https://image.tmdb.org/t/p/w500/poster.jpg")
        assert response.closed

    @pytest.mark.parametrize("data,expected", [
        (JPEG, "jpg"),
        (b"\x89PNG\r\n\x1a\nrest", "png"),
        (b"RIFF1234WEBPrest", "webp"),
        (b"<svg onload=alert(1)>", None),
    ])
    def test_image_type(self, data, expected):
        assert image_type(data) == expected


class FakeUser:
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

    def check_visibility(self, visibility):
        return True


@pytest.fixture
def movie_app(tmp_path, monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ub.Base.metadata.create_all(engine)
    db_session = sessionmaker(bind=engine)()
    monkeypatch.setattr(ub, "session", db_session)
    monkeypatch.setattr(ub, "app_DB_path", str(tmp_path / "app.db"))
    monkeypatch.setattr(routes, "render_title_template", lambda template, **context: jsonify(
        template=template,
        entries=[entry.title for entry in context.get("entries", [])],
        entry_sources=[entry.source for entry in context.get("entries", [])],
        total=context.get("total"),
    ))

    app = Flask("cps")
    app.config.update(SECRET_KEY="test", TESTING=True)
    app.register_blueprint(routes.movies)
    app.register_blueprint(jinjia)

    user = FakeUser()
    app.config["TEST_USER"] = user

    @app.before_request
    def authenticate():
        g.flask_httpauth_user = app.config["TEST_USER"]

    monkeypatch.setattr(usermanagement.config, "config_allow_reverse_proxy_header_login", False, raising=False)
    monkeypatch.setattr(usermanagement.config, "config_anonbrowse", 0, raising=False)
    return app, db_session, user


@pytest.mark.unit
class TestMovieRoutes:
    def test_create_search_edit_and_delete(self, movie_app):
        app, db_session, _ = movie_app
        client = app.test_client()
        response = client.post("/movies/new", data={
            "title": "Arrival", "media_format": "4K UHD", "location": "Shelf A",
            "release_date": "2016-11-11", "personal_rating": "9", "is_watched": "on",
        })
        assert response.status_code == 302
        movie = db_session.query(Movie).one()
        assert movie.title == "Arrival"
        assert movie.media_format == "4K UHD"
        assert movie.is_watched
        assert movie.year == "2016"

        response = client.get("/movies/?q=Amy")
        assert response.get_json()["entries"] == []
        response = client.get("/movies/?q=Arrival")
        assert response.get_json()["entries"] == ["Arrival"]
        assert response.get_json()["entry_sources"] == ["movie"]
        response = client.get("/movies/?format=DVD")
        assert response.get_json()["entries"] == []

        response = client.post(f"/movies/{movie.id}/edit", data={
            "title": "Arrival", "media_format": "4K UHD", "location": "Shelf B",
            "personal_rating": "10", "poster": (BytesIO(JPEG), "poster.jpg"),
        }, content_type="multipart/form-data")
        assert response.status_code == 302
        assert movie.location == "Shelf B"
        assert movie.personal_rating == 10
        assert movie.poster_filename.endswith(".jpg")
        poster_response = client.get(f"/movies/{movie.id}/poster")
        assert poster_response.status_code == 200
        assert poster_response.data == JPEG

        response = client.post(f"/movies/{movie.id}/delete")
        assert response.status_code == 302
        assert db_session.query(Movie).count() == 0

    def test_invalid_form_does_not_create_movie(self, movie_app):
        app, db_session, _ = movie_app
        response = app.test_client().post("/movies/new", data={"title": "", "release_date": "not-a-date"})
        assert response.status_code == 400
        assert db_session.query(Movie).count() == 0

    def test_metadata_refresh_preserves_physical_fields(self, movie_app, monkeypatch):
        app, db_session, _ = movie_app
        movie = Movie(title="Old title", media_format="Blu-ray", location="Cabinet 3", barcode="123")
        db_session.add(movie)
        db_session.commit()
        client = TMDBClient(api_key="key", read_access_token="", session=FakeSession(FakeResponse({
            "id": 329865, "title": "Arrival", "overview": "New overview", "release_date": "2016-11-11",
            "credits": {}, "genres": [], "release_dates": {},
        })))
        monkeypatch.setattr(routes, "_client", lambda: client)
        response = app.test_client().post(f"/movies/{movie.id}/metadata/apply", data={"tmdb_id": "329865"})
        assert response.status_code == 302
        assert movie.title == "Arrival"
        assert movie.overview == "New overview"
        assert movie.location == "Cabinet 3"
        assert movie.barcode == "123"
        assert movie.media_format == "Blu-ray"

    @pytest.mark.parametrize("field,value", [
        ("media_format", "Paperback"),
        ("condition", "Scratched"),
    ])
    def test_create_enforces_format_and_condition_membership(self, movie_app, field, value):
        app, db_session, _ = movie_app
        data = {"title": "Arrival", "media_format": "Blu-ray", "condition": "Good", field: value}
        response = app.test_client().post("/movies/new", data=data)
        assert response.status_code == 400
        assert db_session.query(Movie).count() == 0

    def test_edit_enforces_format_and_condition_membership(self, movie_app):
        app, db_session, _ = movie_app
        movie = Movie(title="Arrival", media_format="Blu-ray", condition="Good")
        db_session.add(movie)
        db_session.commit()
        client = app.test_client()
        for data in (
            {"title": "Arrival", "media_format": "Paperback", "condition": "Good"},
            {"title": "Arrival", "media_format": "Blu-ray", "condition": "Scratched"},
        ):
            response = client.post(f"/movies/{movie.id}/edit", data=data)
            assert response.status_code == 400
        assert movie.media_format == "Blu-ray"
        assert movie.condition == "Good"

    def test_import_rejects_invalid_format_before_lookup(self, movie_app, monkeypatch):
        app, db_session, _ = movie_app
        client = SimpleNamespace(details=lambda tmdb_id: pytest.fail("lookup should not run"))
        monkeypatch.setattr(routes, "_client", lambda: client)
        response = app.test_client().post("/movies/import", data={
            "tmdb_id": "329865", "media_format": "Paperback",
        })
        assert response.status_code == 302
        assert db_session.query(Movie).count() == 0

    def test_create_commit_failure_removes_staged_poster(self, movie_app, monkeypatch):
        app, db_session, _ = movie_app

        def fail_commit():
            raise SQLAlchemyError("commit failed")

        monkeypatch.setattr(db_session, "commit", fail_commit)
        response = app.test_client().post("/movies/new", data={
            "title": "Arrival", "media_format": "Blu-ray", "condition": "Good",
            "poster": (BytesIO(JPEG), "poster.jpg"),
        }, content_type="multipart/form-data")
        assert response.status_code == 500
        assert db_session.query(Movie).count() == 0
        assert list(Path(routes._cover_directory()).iterdir()) == []

    def test_edit_commit_failure_keeps_old_poster_and_removes_new_file(self, movie_app, monkeypatch):
        app, db_session, _ = movie_app
        movie = Movie(title="Arrival", media_format="Blu-ray", condition="Good")
        db_session.add(movie)
        db_session.flush()
        old_filename = routes._cover_store().stage(JPEG, "jpg", f"movie-{movie.id}", max_bytes=1024)
        movie.poster_filename = old_filename
        db_session.commit()

        def fail_commit():
            raise SQLAlchemyError("commit failed")

        monkeypatch.setattr(db_session, "commit", fail_commit)
        response = app.test_client().post(f"/movies/{movie.id}/edit", data={
            "title": "Arrival updated", "media_format": "4K UHD", "condition": "New",
            "poster": (BytesIO(JPEG + b"new"), "poster.jpg"),
        }, content_type="multipart/form-data")
        assert response.status_code == 500
        db_session.expire_all()
        movie = db_session.query(Movie).one()
        assert movie.title == "Arrival"
        assert movie.poster_filename == old_filename
        assert [path.name for path in Path(routes._cover_directory()).iterdir()] == [old_filename]

    def test_edit_replaces_old_poster_after_one_successful_commit(self, movie_app, monkeypatch):
        app, db_session, _ = movie_app
        movie = Movie(title="Arrival", media_format="Blu-ray", condition="Good")
        db_session.add(movie)
        db_session.flush()
        old_filename = routes._cover_store().stage(JPEG, "jpg", f"movie-{movie.id}", max_bytes=1024)
        movie.poster_filename = old_filename
        db_session.commit()
        real_commit = db_session.commit
        commits = []

        def counted_commit():
            commits.append(movie.poster_filename)
            return real_commit()

        monkeypatch.setattr(db_session, "commit", counted_commit)
        response = app.test_client().post(f"/movies/{movie.id}/edit", data={
            "title": "Arrival", "media_format": "4K UHD", "condition": "Good",
            "poster": (BytesIO(JPEG + b"new"), "poster.jpg"),
        }, content_type="multipart/form-data")
        assert response.status_code == 302
        assert len(commits) == 1
        assert commits[0] != old_filename
        assert not (Path(routes._cover_directory()) / old_filename).exists()
        assert (Path(routes._cover_directory()) / movie.poster_filename).read_bytes() == JPEG + b"new"

    def test_delete_commit_failure_keeps_movie_and_poster(self, movie_app, monkeypatch):
        app, db_session, _ = movie_app
        movie = Movie(title="Arrival", media_format="Blu-ray")
        db_session.add(movie)
        db_session.flush()
        filename = routes._cover_store().stage(JPEG, "jpg", f"movie-{movie.id}", max_bytes=1024)
        movie.poster_filename = filename
        db_session.commit()

        def fail_commit():
            raise SQLAlchemyError("commit failed")

        monkeypatch.setattr(db_session, "commit", fail_commit)
        response = app.test_client().post(f"/movies/{movie.id}/delete")
        assert response.status_code == 302
        assert db_session.query(Movie).count() == 1
        assert (Path(routes._cover_directory()) / filename).exists()

    def test_import_stages_poster_and_commits_once(self, movie_app, monkeypatch):
        app, db_session, _ = movie_app
        provider = SimpleNamespace(
            details=lambda tmdb_id: {
                "tmdb_id": 329865, "title": "Arrival", "poster_url": "https://image.tmdb.org/t/p/w500/poster.jpg",
            },
            download_poster=lambda url: (JPEG, "jpg"),
        )
        monkeypatch.setattr(routes, "_client", lambda: provider)
        real_commit = db_session.commit
        commits = []

        def counted_commit():
            commits.append(True)
            return real_commit()

        monkeypatch.setattr(db_session, "commit", counted_commit)
        response = app.test_client().post("/movies/import", data={
            "tmdb_id": "329865", "media_format": "Blu-ray", "condition": "Good",
        })
        assert response.status_code == 302
        assert len(commits) == 1
        movie = db_session.query(Movie).one()
        assert movie.poster_filename
        assert (Path(routes._cover_directory()) / movie.poster_filename).read_bytes() == JPEG

    def test_metadata_apply_commit_failure_restores_old_artwork(self, movie_app, monkeypatch):
        app, db_session, _ = movie_app
        movie = Movie(title="Old title", media_format="Blu-ray")
        db_session.add(movie)
        db_session.flush()
        old_filename = routes._cover_store().stage(JPEG, "jpg", f"movie-{movie.id}", max_bytes=1024)
        movie.poster_filename = old_filename
        db_session.commit()
        provider = SimpleNamespace(
            details=lambda tmdb_id: {
                "tmdb_id": 329865, "title": "New title",
                "poster_url": "https://image.tmdb.org/t/p/w500/poster.jpg",
            },
            download_poster=lambda url: (JPEG + b"new", "jpg"),
        )
        monkeypatch.setattr(routes, "_client", lambda: provider)

        def fail_commit():
            raise SQLAlchemyError("commit failed")

        monkeypatch.setattr(db_session, "commit", fail_commit)
        response = app.test_client().post(f"/movies/{movie.id}/metadata/apply", data={"tmdb_id": "329865"})
        assert response.status_code == 302
        db_session.expire_all()
        movie = db_session.query(Movie).one()
        assert movie.title == "Old title"
        assert movie.poster_filename == old_filename
        assert [path.name for path in Path(routes._cover_directory()).iterdir()] == [old_filename]

    def test_edit_permission_is_enforced(self, movie_app):
        app, _, user = movie_app
        user.edit = False
        response = app.test_client().post("/movies/new", data={"title": "Forbidden"})
        assert response.status_code == 403

    def test_delete_permission_is_enforced(self, movie_app):
        app, db_session, user = movie_app
        user.delete = False
        movie = Movie(title="Keep me")
        db_session.add(movie)
        db_session.commit()
        response = app.test_client().post(f"/movies/{movie.id}/delete")
        assert response.status_code == 403
        assert db_session.query(Movie).count() == 1

    def test_movie_pages_render_with_real_templates(self, movie_app, monkeypatch):
        app, db_session, user = movie_app
        movie = Movie(
            title="Arrival", original_title="Arrival", overview="A linguist works with the military.",
            release_date="2016-11-11", runtime=116, director="Denis Villeneuve",
            cast_members="Amy Adams, Jeremy Renner", genres="Drama, Science Fiction",
            media_format="4K UHD", location="Shelf A", edition="Special Edition",
            personal_rating=9, tmdb_rating=7.6, tmdb_id=329865, is_watched=True,
        )
        db_session.add(movie)
        db_session.commit()

        for endpoint in (
            "web.index", "web.profile", "web.logout", "web.login", "web.register",
            "web.create_magic_shelf", "web.render_magic_shelf", "search.simple_search",
            "search.advanced_search", "shelf.create_shelf", "shelf.show_shelf",
            "duplicates.show_duplicates", "duplicates.dismiss_duplicate_scan_setup_notice",
            "about.package_versions", "admin.admin", "edit-book.upload", "tasks.get_tasks_status",
        ):
            app.add_url_rule(f"/stub/{endpoint}", endpoint=endpoint, view_func=lambda: "")

        @app.before_request
        def template_globals():
            g.current_theme = 0
            g.allow_anonymous = False
            g.allow_registration = False
            g.allow_upload = False
            g.shelves_access = []
            g.magic_shelves_access = []
            g.google_site_verification = ""

        app.context_processor(lambda: {
            "current_user": user, "_": lambda text: text, "csrf_token": lambda: "test-token",
        })

        def render(template, **context):
            defaults = {
                "instance": "Home Library", "simple": True, "accept": [],
                "sidebar": [{"visibility": 0, "public": False}],
                "magic_shelf_routes": {"render": False, "create": False},
                "duplicate_notification": {"count": 0}, "searchterm": "", "bodyClass": "",
            }
            defaults.update(context)
            return render_template(template, **defaults)

        monkeypatch.setattr(routes, "render_title_template", render)
        monkeypatch.setattr(routes, "_client", lambda: SimpleNamespace(configured=True))
        client = app.test_client()
        for path, marker in (
            ("/movies/", b"Movies, beautifully organized."),
            (f"/movies/{movie.id}", b"Denis Villeneuve"),
            (f"/movies/{movie.id}/edit", b"Edit Arrival"),
            ("/movies/new", b"Add a movie"),
        ):
            response = client.get(path)
            assert response.status_code == 200, path
            assert marker in response.data, path


@pytest.mark.unit
def test_movie_templates_use_shared_cards_permissions_and_accessible_results():
    template_root = Path(routes.__file__).resolve().parents[1] / "templates" / "movies"
    index = (template_root / "index.html").read_text(encoding="utf-8")
    form = (template_root / "form.html").read_text(encoding="utf-8")
    detail = (template_root / "detail.html").read_text(encoding="utf-8")

    assert '{% from "components/media_card.html" import media_card %}' in index
    assert "{{ media_card(card) }}" in index
    assert 'class="media-grid"' in index
    assert "current_user.role_" not in index + form + detail
    assert 'role="status" aria-live="polite"' in form
    assert 'aria-busy="false"' in form
    assert 'class="media-metadata-results-heading movie-metadata-results-heading" tabindex="-1"' in form


@pytest.mark.unit
def test_movie_metadata_js_preserves_focus_and_safe_dom_construction():
    js_root = Path(routes.__file__).resolve().parents[1] / "static" / "js"
    script = (js_root / "movies.js").read_text(encoding="utf-8")
    shared = (js_root / "metadata_search.js").read_text(encoding="utf-8")

    assert ".innerHTML" not in script
    assert "results.replaceChildren" not in script
    assert "metadataSearch.init({" in script
    assert shared.count("resultsHeading.focus();") == 2
    assert 'results.setAttribute("aria-busy", "true")' in shared
    assert 'results.setAttribute("aria-busy", "false")' in shared
    assert '"X-CSRFToken"' in script
