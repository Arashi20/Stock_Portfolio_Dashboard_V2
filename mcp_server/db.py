"""Database access for the MCP server.

Shares the same Postgres database as the main Flask app (same DATABASE_URL) using
plain SQLAlchemy -- there's no Flask app in this service, so Flask-SQLAlchemy isn't
usable here. `Report` and `Wishlist` below are a structural mirror of the models in
../app.py (same table/column names). This service never creates or migrates those
tables -- app.py's db.create_all() remains the only owner of that schema. If those
models ever change in app.py, mirror the change here too.
"""

import os
import time
from contextlib import contextmanager
from datetime import datetime

import bleach
from bleach.css_sanitizer import CSSSanitizer
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///mcp_local.db")

engine = create_engine(DATABASE_URL, pool_size=2, max_overflow=3, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# KEEP IN SYNC WITH app.py's Report/Wishlist models
# ---------------------------------------------------------------------------

class Report(Base):
    __tablename__ = "report"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False)
    title = Column(String(200), nullable=False)
    date = Column(DateTime, nullable=False)
    notes = Column(Text, nullable=False)
    date_created = Column(DateTime, default=datetime.utcnow)


class Wishlist(Base):
    __tablename__ = "wishlist"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, unique=True)
    target_price = Column(Float, nullable=False)
    currency = Column(String(10), default="$")
    date_added = Column(DateTime, default=datetime.utcnow)

# ---------------------------------------------------------------------------
# End of mirrored models
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tables owned exclusively by this service: OAuth state, persisted (not
# in-memory) because a Railway redeploy replaces the running process.
# ---------------------------------------------------------------------------

class OAuthLoginState(Base):
    """A pending authorization request, alive only for the login redirect round-trip."""

    __tablename__ = "mcp_oauth_login_state"

    state = Column(String(64), primary_key=True)
    client_id = Column(String(200), nullable=False)
    redirect_uri = Column(Text, nullable=False)
    redirect_uri_provided_explicitly = Column(Boolean, nullable=False)
    code_challenge = Column(String(200), nullable=False)
    scopes = Column(Text, nullable=False)  # space-separated
    resource = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OAuthAuthCode(Base):
    __tablename__ = "mcp_oauth_auth_code"

    code = Column(String(64), primary_key=True)
    client_id = Column(String(200), nullable=False)
    redirect_uri = Column(Text, nullable=False)
    redirect_uri_provided_explicitly = Column(Boolean, nullable=False)
    code_challenge = Column(String(200), nullable=False)
    scopes = Column(Text, nullable=False)
    resource = Column(Text, nullable=True)
    subject = Column(String(200), nullable=True)
    expires_at = Column(Float, nullable=False)


class OAuthTokenRecord(Base):
    __tablename__ = "mcp_oauth_token"

    token = Column(String(64), primary_key=True)
    token_kind = Column(String(20), nullable=False)  # 'access' or 'refresh'
    client_id = Column(String(200), nullable=False)
    scopes = Column(Text, nullable=False)
    subject = Column(String(200), nullable=True)
    expires_at = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_oauth_tables():
    """Create only the tables this service owns. Never touches report/wishlist."""
    Base.metadata.create_all(bind=engine, tables=[
        OAuthLoginState.__table__,
        OAuthAuthCode.__table__,
        OAuthTokenRecord.__table__,
    ])


# ---------------------------------------------------------------------------
# HTML sanitization -- copied verbatim from app.py's sanitize_html() so
# Report.notes gets identical treatment regardless of which service wrote it.
# ---------------------------------------------------------------------------

def sanitize_html(html_content):
    """Sanitize HTML content to prevent XSS attacks"""
    allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'h2', 'h3', 'ul', 'ol', 'li', 'b', 'i']
    allowed_attributes = {
        '*': ['style'],
    }
    css_sanitizer = CSSSanitizer(allowed_css_properties=['text-align'])
    cleaned_html = bleach.clean(
        html_content,
        tags=allowed_tags,
        attributes=allowed_attributes,
        css_sanitizer=css_sanitizer,
        strip=True
    )
    return cleaned_html


# ---------------------------------------------------------------------------
# Report / Wishlist query helpers used by the MCP tools in server.py.
# Validation mirrors app.py's create_report/add_to_wishlist routes exactly.
# ---------------------------------------------------------------------------

class ValidationError(Exception):
    """Raised for bad tool input -- caught in server.py and turned into a tool error."""


class DuplicateTickerError(Exception):
    """Raised when a wishlist ticker already exists."""


def create_report(ticker: str, title: str, date_str: str, notes: str) -> dict:
    ticker = (ticker or "").upper().strip()
    title = (title or "").strip()
    notes = (notes or "").strip()

    if not ticker or not title or not notes:
        raise ValidationError("ticker, title, and notes are all required.")

    try:
        report_date = datetime.strptime(date_str, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValidationError("date must be in YYYY-MM-DD format.")

    sanitized_notes = sanitize_html(notes)

    with session_scope() as session:
        report = Report(ticker=ticker, title=title, date=report_date, notes=sanitized_notes)
        session.add(report)
        session.flush()
        return {"id": report.id, "ticker": report.ticker, "title": report.title,
                "date": report.date.strftime("%Y-%m-%d")}


def list_reports(ticker: str | None = None, limit: int = 20) -> list[dict]:
    limit = max(1, min(limit, 100))
    with session_scope() as session:
        query = session.query(Report)
        if ticker:
            query = query.filter(Report.ticker == ticker.upper().strip())
        rows = query.order_by(Report.date_created.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "ticker": r.ticker,
                "title": r.title,
                "date": r.date.strftime("%Y-%m-%d"),
                "date_created": r.date_created.strftime("%Y-%m-%d %H:%M"),
            }
            for r in rows
        ]


def add_wishlist_item(ticker: str, target_price: float, currency: str = "$") -> dict:
    ticker = (ticker or "").upper().strip()
    if not ticker:
        raise ValidationError("ticker is required.")

    try:
        target_price = float(target_price)
    except (TypeError, ValueError):
        raise ValidationError("target_price must be a number.")

    if not (0 < target_price < 10_000_000):
        raise ValidationError("target_price must be a positive, realistic number.")

    currency = (currency or "$").strip() or "$"

    with session_scope() as session:
        existing = session.query(Wishlist).filter_by(ticker=ticker).first()
        if existing:
            raise DuplicateTickerError(f"{ticker} is already in the wishlist.")

        item = Wishlist(ticker=ticker, target_price=target_price, currency=currency)
        session.add(item)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise DuplicateTickerError(f"{ticker} is already in the wishlist.")
        return {"id": item.id, "ticker": item.ticker, "target_price": item.target_price,
                "currency": item.currency}


def list_wishlist() -> list[dict]:
    with session_scope() as session:
        rows = session.query(Wishlist).order_by(Wishlist.date_added.desc()).all()
        return [
            {
                "id": w.id,
                "ticker": w.ticker,
                "target_price": w.target_price,
                "currency": w.currency,
                "date_added": w.date_added.strftime("%Y-%m-%d"),
            }
            for w in rows
        ]


# ---------------------------------------------------------------------------
# OAuth state helpers
# ---------------------------------------------------------------------------

def save_login_state(state, client_id, redirect_uri, redirect_uri_provided_explicitly,
                      code_challenge, scopes, resource):
    with session_scope() as session:
        session.add(OAuthLoginState(
            state=state,
            client_id=client_id,
            redirect_uri=redirect_uri,
            redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
            code_challenge=code_challenge,
            scopes=" ".join(scopes or []),
            resource=resource,
        ))


def pop_login_state(state):
    with session_scope() as session:
        row = session.query(OAuthLoginState).filter_by(state=state).first()
        if not row:
            return None
        data = {
            "client_id": row.client_id,
            "redirect_uri": row.redirect_uri,
            "redirect_uri_provided_explicitly": row.redirect_uri_provided_explicitly,
            "code_challenge": row.code_challenge,
            "scopes": row.scopes.split(" ") if row.scopes else [],
            "resource": row.resource,
        }
        session.delete(row)
        return data


def save_auth_code(code, client_id, redirect_uri, redirect_uri_provided_explicitly,
                    code_challenge, scopes, resource, subject, ttl_seconds=300):
    with session_scope() as session:
        session.add(OAuthAuthCode(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            redirect_uri_provided_explicitly=redirect_uri_provided_explicitly,
            code_challenge=code_challenge,
            scopes=" ".join(scopes or []),
            resource=resource,
            subject=subject,
            expires_at=time.time() + ttl_seconds,
        ))


def load_auth_code(code):
    with session_scope() as session:
        row = session.query(OAuthAuthCode).filter_by(code=code).first()
        if not row:
            return None
        return {
            "code": row.code,
            "client_id": row.client_id,
            "redirect_uri": row.redirect_uri,
            "redirect_uri_provided_explicitly": row.redirect_uri_provided_explicitly,
            "code_challenge": row.code_challenge,
            "scopes": row.scopes.split(" ") if row.scopes else [],
            "resource": row.resource,
            "subject": row.subject,
            "expires_at": row.expires_at,
        }


def delete_auth_code(code):
    with session_scope() as session:
        session.query(OAuthAuthCode).filter_by(code=code).delete()


def save_token(token, token_kind, client_id, scopes, subject, expires_at):
    with session_scope() as session:
        session.add(OAuthTokenRecord(
            token=token,
            token_kind=token_kind,
            client_id=client_id,
            scopes=" ".join(scopes or []),
            subject=subject,
            expires_at=expires_at,
        ))


def load_token(token, token_kind):
    with session_scope() as session:
        row = session.query(OAuthTokenRecord).filter_by(token=token, token_kind=token_kind).first()
        if not row:
            return None
        if row.expires_at and row.expires_at < time.time():
            session.delete(row)
            return None
        return {
            "token": row.token,
            "client_id": row.client_id,
            "scopes": row.scopes.split(" ") if row.scopes else [],
            "subject": row.subject,
            "expires_at": row.expires_at,
        }


def delete_token(token):
    with session_scope() as session:
        session.query(OAuthTokenRecord).filter_by(token=token).delete()
