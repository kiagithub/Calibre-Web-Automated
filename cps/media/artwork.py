# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

"""Atomic artwork files stored beside the application database."""

import os
import uuid

from flask import send_file

from .. import constants
from .images import image_type


class ArtworkStore:
    def __init__(self, database_path, subdirectory):
        if not database_path:
            raise RuntimeError("The application database path is not initialized.")
        if (not subdirectory or os.path.basename(subdirectory) != subdirectory
                or any(separator in subdirectory for separator in "/\\")):
            raise ValueError("Artwork directory must be a basename.")
        self.root = os.path.join(os.path.dirname(os.path.abspath(database_path)), subdirectory)

    def path(self, filename):
        self._validate_filename(filename)
        return os.path.join(self.root, filename)

    def stage(self, data, extension, prefix, *, max_bytes):
        """Atomically write a new uniquely named image and return its basename."""
        actual_extension = image_type(data)
        if not actual_extension or actual_extension != extension or len(data) > max_bytes:
            raise ValueError("Unsupported or oversized artwork image")
        if not prefix or os.path.basename(prefix) != prefix or any(c in prefix for c in "/\\\x00"):
            raise ValueError("Invalid artwork filename prefix")
        filename = f"{prefix}-{uuid.uuid4().hex}.{actual_extension}"
        destination = self.path(filename)
        temporary = self.path(f".{filename}.{uuid.uuid4().hex}.tmp")
        os.makedirs(self.root, mode=0o750, exist_ok=True)
        try:
            with open(temporary, "xb") as artwork_file:
                artwork_file.write(data)
            os.replace(temporary, destination)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return filename

    def discard(self, filename):
        """Remove an uncommitted staged file, if it still exists."""
        self.delete(filename)

    def delete(self, filename):
        if not filename:
            return
        try:
            os.unlink(self.path(filename))
        except FileNotFoundError:
            pass

    @staticmethod
    def _validate_filename(filename):
        if (not filename or os.path.basename(filename) != filename
                or any(separator in filename for separator in "/\\")
                or filename in (".", "..") or "\x00" in filename):
            raise ValueError("Invalid artwork filename")


def serve_artwork(store, filename):
    """Serve stored artwork with consistent private caching and fallback."""
    if filename:
        try:
            path = store.path(filename)
            if os.path.isfile(path):
                response = send_file(path, conditional=True, max_age=3600)
                response.headers["Cache-Control"] = "private, max-age=3600"
                return response
        except ValueError:
            pass
    return send_file(os.path.join(constants.BASE_DIR, "cps", "static", "generic_cover.svg"))
