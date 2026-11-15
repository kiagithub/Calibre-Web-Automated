# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later


def escaped_like(value):
    """Escape user text for a SQL LIKE expression with backslash escaping."""
    escaped = (value or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
