# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Keep legacy tests from leaking stubbed modules into later test files.

Several older test modules replace ``cps``, Flask, and SQLAlchemy entries in
``sys.modules`` with stubs while loading a module from disk. They do not put
the real modules back, which makes a single-process test run order-dependent.
This fixture snapshots and restores only the modules those tests touch.
"""

import sys
from pathlib import Path

import pytest

_ISOLATED_TEST_FILES = {
    "test_calibre_init.py",
    "test_duplicate_delete_index_maintenance.py",
    "test_duplicate_index.py",
    "test_duplicate_scan_index_rewire.py",
    "test_duplicate_scan_queue_settings.py",
    "test_duplicates_timezone.py",
}


def _is_relevant(name):
    return (
        name == "cps"
        or name.startswith("cps.")
        or name == "cwa_db"
        or name == "flask"
        or name.startswith("flask.")
        or name == "flask_babel"
        or name == "sqlalchemy"
        or name.startswith("sqlalchemy.")
        or name == "werkzeug"
        or name.startswith("werkzeug.")
    )


@pytest.fixture(autouse=True, scope="module")
def restore_legacy_modules(request):
    """Restore real modules after a legacy test module finishes."""
    test_file = Path(getattr(request.module, "__file__", "") or "").name
    if test_file not in _ISOLATED_TEST_FILES:
        yield
        return

    snapshot = {
        name: module for name, module in sys.modules.items() if _is_relevant(name)
    }
    try:
        yield
    finally:
        for name in [name for name in sys.modules if _is_relevant(name)]:
            if name not in snapshot:
                sys.modules.pop(name, None)
        sys.modules.update(snapshot)
