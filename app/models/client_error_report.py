from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .base import Base


class ClientErrorReportRecord(Base):
    __tablename__ = "client_error_reports"

    id = Column(Integer, primary_key=True, index=True)
    app = Column(String(64), nullable=False, index=True)
    source = Column(String(128), nullable=False, index=True)
    message = Column(Text, nullable=False)
    fingerprint = Column(String(128), nullable=False, index=True)
    stack = Column(Text, nullable=True)
    url = Column(String(2000), nullable=True)
    route = Column(String(512), nullable=True, index=True)
    user_agent = Column(String(1024), nullable=True)
    client_ip = Column(String(64), nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    deduplicated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
