# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from cps.media.preferences import catalog_defaults, set_catalog_defaults


class DummyUser:
    def __init__(self, user_id=1, view_settings=None):
        self.id = user_id
        self.view_settings = view_settings or {}


@pytest.mark.unit
def test_catalog_defaults_handles_missing_or_invalid_settings():
    assert catalog_defaults(None) == {}
    assert catalog_defaults(DummyUser(view_settings=None)) == {}
    assert catalog_defaults(DummyUser(view_settings={"catalog": "invalid"})) == {}
    assert catalog_defaults(DummyUser(view_settings={"catalog": {"source": "unknown"}})) == {}


@pytest.mark.unit
def test_catalog_defaults_extracts_valid_values():
    user = DummyUser(view_settings={"catalog": {"source": "external", "media_type": "kindle"}})
    defaults = catalog_defaults(user)
    assert defaults == {"source": "external", "media_type": "kindle"}


@pytest.mark.unit
def test_set_catalog_defaults_persists_and_cleans_values(monkeypatch):
    user = DummyUser(view_settings={})
    committed = []

    class DummySession:
        def commit(self):
            committed.append(True)

        def rollback(self):
            pass

    import cps.ub as ub
    monkeypatch.setattr(ub, "session", DummySession())

    # Set initial defaults
    success = set_catalog_defaults(user, {"source": "external", "media_type": "audiobook"})
    assert success is True
    assert user.view_settings["catalog"] == {"source": "external", "media_type": "audiobook"}
    assert len(committed) == 1

    # Reset source to "all" removes it from stored dict
    set_catalog_defaults(user, {"source": "all"})
    assert "source" not in user.view_settings["catalog"]
    assert user.view_settings["catalog"]["media_type"] == "audiobook"


@pytest.mark.unit
def test_set_catalog_defaults_fails_gracefully_for_anonymous():
    assert set_catalog_defaults(None, {"source": "external"}) is False
    assert set_catalog_defaults(DummyUser(user_id=None), {"source": "external"}) is False
