# Calibre-Web Automated – fork of Calibre-Web
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..ub import Base


def utc_now():
    return datetime.now(timezone.utc)


class ApiKey(Base):
    __tablename__ = "api_key"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(100), nullable=False, default="API key")
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    readonly = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    last_used_at = Column(DateTime)
    revoked_at = Column(DateTime)

    user = relationship("User")

    def __repr__(self):
        return f"<ApiKey {self.id}: {self.name!r}>"
