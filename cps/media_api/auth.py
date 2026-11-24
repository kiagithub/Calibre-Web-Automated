# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
from datetime import datetime, timezone
from functools import wraps

from flask import g, jsonify, request

from .. import ub
from .models import ApiKey


def hash_key(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _token():
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.headers.get("X-Api-Key", "").strip()


def api_key_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        token = _token()
        if not token:
            return jsonify({"error": "Unauthorized"}), 401
        key = (
            ub.session.query(ApiKey)
            .filter(ApiKey.key_hash == hash_key(token))
            .filter(ApiKey.revoked_at.is_(None))
            .first()
        )
        if key is None:
            return jsonify({"error": "Unauthorized"}), 401
        user = ub.session.get(ub.User, key.user_id)
        if user is None:
            return jsonify({"error": "Unauthorized"}), 401
        key.last_used_at = datetime.now(timezone.utc)
        try:
            ub.session.commit()
        except Exception:
            ub.session.rollback()
        g.api_user = user
        g.api_key = key
        return func(*args, **kwargs)

    return wrapper
