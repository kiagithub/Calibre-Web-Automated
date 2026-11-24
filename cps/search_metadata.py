# -*- coding: utf-8 -*-
# Calibre-Web Automated – fork of Calibre-Web
# Copyright (C) 2018-2025 Calibre-Web contributors
# Copyright (C) 2024-2025 Calibre-Web Automated contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# See CONTRIBUTORS for full list of authors.

import concurrent.futures
import importlib
import inspect
import os
import sys
import threading
import time
from collections import OrderedDict

from flask import Blueprint, request, url_for, make_response, jsonify, copy_current_request_context
from .cw_login import current_user
from flask_babel import get_locale
from sqlalchemy.exc import InvalidRequestError, OperationalError
from sqlalchemy.orm.attributes import flag_modified

from cps.services.Metadata import Metadata
from . import constants, logger, ub, web_server
from .metadata_merge import dedupe_records
from .usermanagement import user_login_required


meta = Blueprint("metadata", __name__)

log = logger.create()

# Metadata providers are independent network calls. Run them side by side and
# stop waiting once the deadline passes so one slow provider cannot hold up the
# whole result set. Complete result sets are cached briefly to make repeated
# searches (and the automatic cover-thumbnail retries) instant.
try:
    METADATA_SEARCH_TIMEOUT = max(
        0.5, float(os.environ.get("CWA_METADATA_SEARCH_TIMEOUT", "10"))
    )
except ValueError:
    METADATA_SEARCH_TIMEOUT = 10.0
METADATA_SEARCH_GRACE = 4.0
METADATA_SEARCH_MAX_WORKERS = 16
METADATA_SEARCH_CACHE_TTL = 300
METADATA_SEARCH_CACHE_SIZE = 64

_search_cache = OrderedDict()
_search_cache_lock = threading.Lock()

try:
    from dataclasses import asdict
except ImportError:
    log.info('*** "dataclasses" is needed for calibre-web automated to run. Please install it using pip: "pip install dataclasses" ***')
    print('*** "dataclasses" is needed for calibre-web automated to run. Please install it using pip: "pip install dataclasses" ***')
    web_server.stop(True)
    sys.exit(6)

new_list = list()
meta_dir = os.path.join(constants.BASE_DIR, "cps", "metadata_provider")
modules = os.listdir(os.path.join(constants.BASE_DIR, "cps", "metadata_provider"))
for f in modules:
    if os.path.isfile(os.path.join(meta_dir, f)) and not f.endswith("__init__.py"):
        a = os.path.basename(f)[:-3]
        try:
            importlib.import_module("cps.metadata_provider." + a)
            new_list.append(a)
        except (IndentationError, SyntaxError) as e:
            log.error("Syntax error for metadata source: {} - {}".format(a, e))
        except ImportError as e:
            log.debug("Import error for metadata source: {} - {}".format(a, e))


def list_classes(provider_list):
    classes = list()
    for element in provider_list:
        for name, obj in inspect.getmembers(
            sys.modules["cps.metadata_provider." + element]
        ):
            if (
                inspect.isclass(obj)
                and name != "Metadata"
                and issubclass(obj, Metadata)
            ):
                classes.append(obj())
    return classes


cl = list_classes(new_list)
# Alphabetises the list of Metadata providers
cl.sort(key=lambda x: x.__class__.__name__)


def _enabled_providers(active, global_enabled):
    """Return providers enabled for this user and globally, in stable order."""
    return [
        provider for provider in cl
        if active.get(provider.__id__, True) and bool(global_enabled.get(provider.__id__, True))
    ]


def _cache_key(query, locale, providers, search_by=""):
    """Scope cached results to the query, locale, user, provider set, and search target."""
    try:
        user_id = getattr(current_user, "id", None)
    except Exception:
        user_id = None
    query_str = f"{search_by}:{query}" if search_by else str(query)
    return (
        " ".join(query_str.split()).casefold(),
        str(locale),
        user_id,
        tuple(sorted(provider.__id__ for provider in providers)),
    )


def _cache_get(key, now=None):
    now = time.monotonic() if now is None else now
    with _search_cache_lock:
        entry = _search_cache.get(key)
        if entry is None:
            return None
        expires, data = entry
        if expires <= now:
            _search_cache.pop(key, None)
            return None
        _search_cache.move_to_end(key)
        return list(data)


def _cache_set(key, data, now=None):
    now = time.monotonic() if now is None else now
    with _search_cache_lock:
        _search_cache[key] = (now + METADATA_SEARCH_CACHE_TTL, list(data))
        _search_cache.move_to_end(key)
        while len(_search_cache) > METADATA_SEARCH_CACHE_SIZE:
            _search_cache.popitem(last=False)


def _clear_search_cache():
    """Test helper: forget every cached metadata result."""
    with _search_cache_lock:
        _search_cache.clear()


def _search_providers(query, providers, static_cover, locale, deadline=None, search_by=""):
    """Search providers concurrently and return (results, partial).

    ``partial`` is true when providers were still running at the deadline or
    after the grace window that follows the first completed provider. Running
    calls are abandoned rather than blocking the response; they are bounded by
    each provider's own request timeout.
    """
    if not providers:
        return [], False
    deadline = METADATA_SEARCH_TIMEOUT if deadline is None else deadline
    grace = min(METADATA_SEARCH_GRACE, deadline)
    started = time.monotonic()
    deadline_at = started + deadline
    first_done_at = None
    results_by_order = {}
    futures = {}
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(len(providers), METADATA_SEARCH_MAX_WORKERS))
    )
    try:
        for order, provider in enumerate(providers):
            search = copy_current_request_context(provider.search)
            try:
                sig = inspect.signature(provider.search)
            except (ValueError, TypeError):
                sig = None
            if sig and "search_by" in sig.parameters:
                futures[executor.submit(search, query, static_cover, locale, search_by=search_by)] = (order, provider)
            elif search_by == "title" and getattr(provider, "__id__", "") == "google":
                futures[executor.submit(search, f"intitle:{query}", static_cover, locale)] = (order, provider)
            elif search_by == "author" and getattr(provider, "__id__", "") == "google":
                futures[executor.submit(search, f"inauthor:{query}", static_cover, locale)] = (order, provider)
            elif search_by == "isbn" and getattr(provider, "__id__", "") == "google":
                futures[executor.submit(search, f"isbn:{query}", static_cover, locale)] = (order, provider)
            else:
                futures[executor.submit(search, query, static_cover, locale)] = (order, provider)

        remaining = set(futures)
        while remaining:
            now = time.monotonic()
            # Once the first provider answers, give stragglers a short grace
            # window instead of waiting for the slowest one up to the deadline.
            wait_until = deadline_at
            if first_done_at is not None:
                wait_until = min(wait_until, first_done_at + grace)
            if now >= wait_until:
                break
            done, remaining = concurrent.futures.wait(
                remaining,
                timeout=wait_until - now,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            if not done:
                break
            if first_done_at is None:
                first_done_at = time.monotonic()
            for future in done:
                order, provider = futures[future]
                try:
                    result = future.result()
                    if result:
                        results_by_order[order] = [asdict(record) for record in result if record]
                except Exception as exc:
                    log.warning(
                        "Metadata provider %s failed: %s", provider.__class__.__name__, exc
                    )
        partial = bool(remaining)
    finally:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

    data = []
    for order in sorted(results_by_order):
        data.extend(results_by_order[order])
    return data, partial


# Helper to load global provider enablement map from CWA settings
def _get_global_provider_enabled_map() -> dict:
    try:
        # Import here to avoid circular import issues and keep startup fast
        sys.path.insert(1, '/app/calibre-web-automated/scripts/')
        from cwa_db import CWA_DB  # type: ignore
        cwa_db = CWA_DB()
        settings = cwa_db.get_cwa_settings()
        
        if not settings:
            log.warning("Could not get CWA settings for provider enabled map")
            return {}
        
        from cps.cwa_functions import parse_metadata_providers_enabled
        return parse_metadata_providers_enabled(
            settings.get('metadata_providers_enabled', '{}')
        )
    except Exception as e:
        # On any failure, treat as all enabled (empty dict = all default to enabled)
        log.warning(f"Error loading provider enabled map: {e}")
        return {}
    # Remove redundant return

@meta.route("/metadata/provider")
@user_login_required
def metadata_provider():
    active = current_user.view_settings.get("metadata", {})
    global_enabled = _get_global_provider_enabled_map()
    provider = list()
    for c in cl:
        ac = active.get(c.__id__, True)
        provider.append(
            {
                "name": c.__name__,
                "active": ac,
                "initial": ac,
                "id": c.__id__,
                "globally_enabled": bool(global_enabled.get(c.__id__, True)),
            }
        )
    return make_response(jsonify(provider))


@meta.route("/metadata/provider", methods=["POST"])
@meta.route("/metadata/provider/<prov_name>", methods=["POST"])
@user_login_required
def metadata_change_active_provider(prov_name):
    new_state = request.get_json()
    active = current_user.view_settings.get("metadata", {})
    active[new_state["id"]] = new_state["value"]
    current_user.view_settings["metadata"] = active
    try:
        try:
            flag_modified(current_user, "view_settings")
        except AttributeError:
            pass
        ub.session.commit()
    except (InvalidRequestError, OperationalError):
        log.error("Invalid request received: {}".format(request))
        return "Invalid request", 400
    if "initial" in new_state and prov_name:
        data = []
        provider = next((c for c in cl if c.__id__ == prov_name), None)
        # Respect global disablement for preview search as well
        global_enabled = _get_global_provider_enabled_map()
        if provider is not None:
            if bool(global_enabled.get(provider.__id__, True)):
                try:
                    data = provider.search(new_state.get("query", ""))
                except Exception as exc:
                    log.warning("Metadata provider %s failed: %s", provider.__class__.__name__, exc)
                    data = []
            else:
                data = []
        if not data:
            return make_response(jsonify([]))
        return make_response(jsonify([asdict(x) for x in data if x]))
    return ""


@meta.route("/metadata/search", methods=["POST"])
@user_login_required
def metadata_search():
    form = request.form.to_dict()
    query = (form.get("query") or "").strip()[:300]
    search_by = (form.get("search_by") or "").strip().lower()[:20]
    if search_by not in ("title", "author", "isbn"):
        search_by = ""
    owned = (form.get("owned") or "").strip().lower()[:10]
    check_owned = str(form.get("check_owned", "")).lower() in ("1", "true", "on") or bool(owned)
    if not query:
        return make_response(jsonify([]))
    active = current_user.view_settings.get("metadata", {})
    locale = get_locale()
    global_enabled = _get_global_provider_enabled_map()
    providers = _enabled_providers(active, global_enabled)
    key = _cache_key(query, locale, providers, search_by=search_by)
    cached = _cache_get(key)
    partial = False
    if cached is not None:
        data = cached
    else:
        static_cover = url_for("static", filename="generic_cover.svg")
        data, partial = _search_providers(query, providers, static_cover, locale, search_by=search_by)
        data = dedupe_records(data)
        if not partial:
            _cache_set(key, data)

    if check_owned and data:
        from .media.library_check import annotate_books

        data = annotate_books([dict(item) for item in data])

    if owned == "hide":
        data = [item for item in data if not item.get("owned")]
    elif owned == "only":
        data = [item for item in data if item.get("owned")]

    response = make_response(jsonify(data))
    if partial:
        response.headers["X-Metadata-Partial"] = "true"
    return response
