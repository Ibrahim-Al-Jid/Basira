"""Local email/password accounts. Project authorization uses the existing platform session."""
from functools import lru_cache
import hashlib
import os
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from .identity import (
    PASSWORD_ISSUER, account_view, issue_session, normalize_person_name, oidc_settings, password_auth_enabled,
    session_digest, set_platform_cookie,
)
from .platform_db import Base, PlatformUnavailable, User, bind_owner, new_id, platform_session, utc_now

HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
EMAIL = re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+")
WINDOW_SECONDS = 900
router = APIRouter(prefix="/api/platform/auth", tags=["Project identity"])

credentials = sa.Table(
    "password_credentials", Base.metadata,
    sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("password_hash", sa.String(255), nullable=False),
)
limits = sa.Table(
    "password_attempt_limits", Base.metadata,
    sa.Column("scope", sa.String(80), primary_key=True),
    sa.Column("window", sa.BigInteger, primary_key=True, index=True),
    sa.Column("attempts", sa.Integer, nullable=False),
)


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        email = value.strip().lower()
        if not EMAIL.fullmatch(email):
            raise ValueError("Invalid email")
        local, domain = email.split("@")
        if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local or any(
            len(label) > 63 for label in domain.split(".")
        ):
            raise ValueError("Invalid email")
        return email

    @field_validator("password")
    @classmethod
    def valid_password_text(cls, password):
        value = password.get_secret_value()
        if "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("Invalid password text")
        return password


class Registration(Credentials):
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_name(cls, value):
        return normalize_person_name(value) if value is not None else None

    @model_validator(mode="after")
    def name_pair(self):
        if (self.first_name is None) != (self.last_name is None):
            raise ValueError("Both names are required together")
        return self


def registration(request):
    return password_auth_enabled(request) and os.environ.get("BASIRA_PASSWORD_SELF_SIGNUP") == "1"


@router.get("/options")
def options(request: Request):
    try:
        oidc_settings()
        oidc = bool(os.environ.get("BASIRA_PLATFORM_DATABASE_URL"))
    except PlatformUnavailable:
        oidc = False
    return {"oidc": oidc, "password": password_auth_enabled(request), "registration": registration(request)}


def reserve_attempt(request, email, action):
    window = int(utc_now().timestamp()) // WINDOW_SECONDS
    peer = request.client.host if request.client else "unknown"
    keys = [("peer", peer, 12 if action == "register" else 30),
            # Keyed by caller and email together: a key on the email alone lets anyone lock a known account out
            # by failing logins for it from anywhere.
            ("peer-email", f"{peer}|{email}", 6 if action == "register" else 8)]
    allowed = True
    with platform_session() as db:
        postgres = db.bind.dialect.name == "postgresql"
        insert = pg_insert if postgres else sqlite_insert
        if not postgres:
            db.execute(limits.delete().where(limits.c.window < window - 1))
        for kind, value, limit in keys:
            digest = hashlib.sha256(value.encode()).hexdigest()
            scope = f"{action}:{kind}:{digest}"
            if postgres:
                # The counter is definer-only: no account is known yet, so no owner policy can scope it.
                result = db.scalar(sa.text(
                    "SELECT public.basira_reserve_attempt("
                    "CAST(:scope AS text), CAST(:window AS bigint), CAST(:limit AS integer))"),
                    {"scope": scope, "window": window, "limit": limit})
            else:
                query = insert(limits).values(scope=scope, window=window, attempts=1)
                result = db.execute(query.on_conflict_do_update(
                    index_elements=[limits.c.scope, limits.c.window],
                    set_={"attempts": limits.c.attempts + 1}, where=limits.c.attempts < limit,
                ).returning(limits.c.attempts)).scalar_one_or_none()
            if result is None:
                allowed = False
                if kind == "peer":
                    break
    if not allowed:
        raise HTTPException(429, "وصلت لحد محاولات الدخول. حاول بعد شوية.",
                            headers={"Retry-After": str(WINDOW_SECONDS)})


@lru_cache(maxsize=1)
def dummy_password_hash():
    return HASHER.hash(secrets.token_urlsafe(32))


def authenticated(request, response, token, user):
    set_platform_cookie(response, token, secure=request.url.scheme == "https")
    return account_view(user)


@router.post("/password/register", status_code=201)
def register(body: Registration, request: Request, response: Response):
    if not registration(request):
        raise HTTPException(403, "إنشاء حساب بالإيميل مش متاح في الإعدادات دي.")
    password = body.password.get_secret_value()
    if len(password) < 12 or not password.strip():
        raise HTTPException(422, "استخدم كلمة مرور من ١٢ حرف على الأقل.")
    reserve_attempt(request, body.email, "register")
    encoded = HASHER.hash(password)
    try:
        with platform_session() as db:
            user = User(id=new_id(), issuer=PASSWORD_ISSUER, subject=body.email,
                        first_name=body.first_name, last_name=body.last_name,
                        display_name=f"{body.first_name} {body.last_name}" if body.first_name else "")
            bind_owner(db, user.id)
            db.add(user)
            db.flush()
            db.execute(credentials.insert().values(user_id=user.id, password_hash=encoded))
            token = issue_session(db, user.id, session_digest(request))
    except IntegrityError:
        raise HTTPException(409, "تعذّر إنشاء الحساب. جرّب تسجيل الدخول أو اختار إيميل تاني.") from None
    return authenticated(request, response, token, user)


@router.post("/password/login")
def login(body: Credentials, request: Request, response: Response):
    if not password_auth_enabled(request):
        raise HTTPException(403, "الدخول بالإيميل مش متاح في الإعدادات دي.")
    reserve_attempt(request, body.email, "login")
    dummy = dummy_password_hash()
    with platform_session() as db:
        if db.get_bind().dialect.name == "postgresql":
            found = db.execute(sa.text(
                "SELECT user_id, password_hash FROM public.basira_login_identity(:issuer, :subject)"),
                {"issuer": PASSWORD_ISSUER, "subject": body.email}).first()
            user_id, password_hash = (found[0], found[1]) if found else (None, None)
        else:
            row = db.execute(sa.select(User.id, credentials.c.password_hash).join(
                credentials, credentials.c.user_id == User.id,
            ).where(User.issuer == PASSWORD_ISSUER, User.subject == body.email)).one_or_none()
            user_id, password_hash = (row[0], row[1]) if row is not None else (None, None)
        encoded = password_hash if password_hash else dummy
    try:
        valid = HASHER.verify(encoded, body.password.get_secret_value())
    except (VerificationError, InvalidHashError, UnicodeError):
        valid = False
    if not valid or user_id is None:
        raise HTTPException(401, "الإيميل أو كلمة المرور غير صحيحة.")
    with platform_session() as db:
        bind_owner(db, user_id)
        user = db.get(User, user_id)
        if user is None or user.disabled_at is not None:
            raise HTTPException(401, "الإيميل أو كلمة المرور غير صحيحة.")
        if HASHER.check_needs_rehash(encoded):
            db.execute(credentials.update().where(credentials.c.user_id == user.id,
                       credentials.c.password_hash == encoded).values(
                           password_hash=HASHER.hash(body.password.get_secret_value())))
        token = issue_session(db, user.id, session_digest(request))
    return authenticated(request, response, token, user)
