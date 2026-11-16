# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import time

import pytest
from flask import Flask, g

from cps import search_metadata, usermanagement
from cps.search_metadata import meta
from cps.services.Metadata import MetaRecord, MetaSourceInfo


class FakeUser:
    is_authenticated = True
    is_anonymous = False
    locale = "en"
    id = 1
    name = "Test user"
    view_settings = {}

    def role_upload(self):
        return True

    def role_edit(self):
        return True

    def role_admin(self):
        return False

    def role_delete_books(self):
        return True


class FakeProvider:
    __name__ = "Fake"
    __id__ = "fake"

    def __init__(self, results=None, delay=0.0):
        self.results = results or []
        self.delay = delay
        self.calls = 0

    def search(self, _query, _generic_cover="", _locale="en"):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return list(self.results)


def record(provider_id, title):
    return MetaRecord(
        id=title.lower(),
        title=title,
        authors=["An Author"],
        url="https://example.test/book",
        source=MetaSourceInfo(id=provider_id, description="Fake", link="https://example.test"),
        cover="https://example.test/cover.jpg",
    )


@pytest.fixture
def metadata_app(monkeypatch):
    monkeypatch.setattr(search_metadata, "_get_global_provider_enabled_map", lambda: {})
    monkeypatch.setattr(search_metadata, "get_locale", lambda: "en")
    monkeypatch.setattr(search_metadata, "METADATA_SEARCH_MAX_WORKERS", 8)
    monkeypatch.setattr(search_metadata, "METADATA_SEARCH_TIMEOUT", 0.25)
    search_metadata._clear_search_cache()
    monkeypatch.setattr(usermanagement.config, "config_allow_reverse_proxy_header_login", False, raising=False)
    monkeypatch.setattr(usermanagement.config, "config_anonbrowse", 0, raising=False)

    app = Flask("metadata-search-test")
    app.config.update(SECRET_KEY="test", TESTING=True)
    app.register_blueprint(meta)
    app.config["TEST_USER"] = FakeUser()

    @app.before_request
    def authenticate():
        g.flask_httpauth_user = app.config["TEST_USER"]

    yield app
    search_metadata._clear_search_cache()


@pytest.mark.unit
class TestMetadataSearch:
    def test_slow_provider_does_not_block_fast_results(self, metadata_app, monkeypatch):
        fast = FakeProvider([record("fast", "Fast result")])
        slow = FakeProvider([record("slow", "Slow result")], delay=0.8)
        fast.__id__ = "fast"
        slow.__id__ = "slow"
        monkeypatch.setattr(search_metadata, "cl", [fast, slow])

        started = time.monotonic()
        response = metadata_app.test_client().post("/metadata/search", data={"query": "dune"})
        elapsed = time.monotonic() - started

        assert response.status_code == 200
        assert response.headers.get("X-Metadata-Partial") == "true"
        assert [item["title"] for item in response.get_json()] == ["Fast result"]
        assert elapsed < 0.6

    def test_grace_window_avoids_waiting_for_a_hung_provider(self, metadata_app, monkeypatch):
        fast = FakeProvider([record("fast", "Fast result")])
        hung = FakeProvider([record("hung", "Hung result")], delay=1.5)
        fast.__id__ = "fast"
        hung.__id__ = "hung"
        monkeypatch.setattr(search_metadata, "cl", [fast, hung])
        monkeypatch.setattr(search_metadata, "METADATA_SEARCH_TIMEOUT", 2.0)
        monkeypatch.setattr(search_metadata, "METADATA_SEARCH_GRACE", 0.2)

        started = time.monotonic()
        response = metadata_app.test_client().post("/metadata/search", data={"query": "dune"})
        elapsed = time.monotonic() - started

        assert response.status_code == 200
        assert response.headers.get("X-Metadata-Partial") == "true"
        assert [item["title"] for item in response.get_json()] == ["Fast result"]
        assert elapsed < 0.9

    def test_complete_results_are_cached_per_query(self, metadata_app, monkeypatch):
        provider = FakeProvider([record("fake", "Dune")])
        monkeypatch.setattr(search_metadata, "cl", [provider])
        client = metadata_app.test_client()

        first = client.post("/metadata/search", data={"query": "dune"})
        second = client.post("/metadata/search", data={"query": "  DUNE  "})

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.get_json() == second.get_json()
        assert provider.calls == 1

    def test_empty_query_returns_no_results_without_calling_providers(
        self, metadata_app, monkeypatch
    ):
        provider = FakeProvider([record("fake", "Dune")])
        monkeypatch.setattr(search_metadata, "cl", [provider])

        response = metadata_app.test_client().post("/metadata/search", data={"query": "  "})

        assert response.status_code == 200
        assert response.get_json() == []
        assert provider.calls == 0

    def test_check_owned_annotates_results_without_caching_annotations(
        self, metadata_app, monkeypatch
    ):
        provider = FakeProvider([record("fake", "Dune")])
        monkeypatch.setattr(search_metadata, "cl", [provider])
        import cps.media.library_check as library_check

        def annotate(results):
            for item in results:
                item["owned"] = True
                item["owned_as"] = "Calibre"
            return results

        monkeypatch.setattr(library_check, "annotate_books", annotate)
        client = metadata_app.test_client()

        annotated = client.post(
            "/metadata/search", data={"query": "dune", "check_owned": "1"}
        )
        plain = client.post("/metadata/search", data={"query": "dune"})

        assert annotated.get_json()[0]["owned"] is True
        assert annotated.get_json()[0]["owned_as"] == "Calibre"
        assert "owned" not in plain.get_json()[0]

    def test_disabled_provider_is_not_called(self, metadata_app, monkeypatch):
        enabled = FakeProvider([record("enabled", "Enabled")])
        disabled = FakeProvider([record("disabled", "Disabled")])
        enabled.__id__ = "enabled"
        disabled.__id__ = "disabled"
        metadata_app.config["TEST_USER"].view_settings = {"metadata": {"disabled": False}}
        monkeypatch.setattr(search_metadata, "cl", [enabled, disabled])

        response = metadata_app.test_client().post("/metadata/search", data={"query": "dune"})

        assert [item["title"] for item in response.get_json()] == ["Enabled"]
        assert disabled.calls == 0
