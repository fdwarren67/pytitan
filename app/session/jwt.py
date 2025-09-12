# app/mysession.py
# Self-contained helpers for issuing/verifying access & refresh tokens
# and setting/clearing the refresh cookie.

from __future__ import annotations
import os, time, secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple
import jwt  # PyJWT

# ---- Config (all defined here) ---------------------------------------------

APP_JWT_SECRET = os.environ.get("APP_JWT_SECRET")
APP_REFRESH_SECRET = os.environ.get("APP_REFRESH_SECRET")
if not APP_JWT_SECRET or not APP_REFRESH_SECRET:
    # Fail fast so you don't get mysterious 500s later
    raise RuntimeError("APP_JWT_SECRET and APP_REFRESH_SECRET must be set")

ISS = os.getenv("APP_JWT_ISS", "http://localhost:8000")
AUD = os.getenv("APP_JWT_AUD", "data-service")

ACCESS_TTL = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "900"))  # 15m
REFRESH_TTL = int(os.getenv("REFRESH_TOKEN_TTL_SECONDS", "2592000"))  # 30d

COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "refresh")
COOKIE_PATH = os.getenv("REFRESH_COOKIE_PATH", "/auth/refresh")
COOKIE_SAMESITE = os.getenv("REFRESH_COOKIE_SAMESITE", "Lax")  # "None" for cross-site
COOKIE_SECURE = os.getenv("REFRESH_COOKIE_SECURE", "false").lower() == "true"
COOKIE_HTTPONLY = os.getenv("REFRESH_COOKIE_HTTPONLY", "true").lower() == "true"

# ---- Internals -------------------------------------------------------------


def _now_epoch() -> int:
    return int(time.time())


# ---- Public API ------------------------------------------------------------


def issue_tokens(user: Dict[str, Any], roles: List[str]) -> Tuple[str, int, str, int]:
    """
    Returns: (access_token, access_exp_epoch, refresh_token, refresh_exp_epoch)
    - access token: short-lived, includes sub/email/roles
    - refresh token: long-lived, includes sub/email/roles (+ jti) so /auth/refresh can recreate access token WITH roles
    """
    iat = _now_epoch()
    access_exp = iat + ACCESS_TTL
    refresh_exp = iat + REFRESH_TTL

    access_payload = {
        "iss": ISS,
        "aud": AUD,
        "iat": iat,
        "exp": access_exp,
        "sub": user["sub"],
        "email": user.get("email"),
        "roles": roles,
        "typ": "access",
    }
    access_token = jwt.encode(access_payload, APP_JWT_SECRET, algorithm="HS256")

    jti = secrets.token_urlsafe(24)
    refresh_payload = {
        "iss": ISS,
        "aud": AUD,
        "iat": iat,
        "exp": refresh_exp,
        "sub": user["sub"],
        "email": user.get("email"),
        "roles": roles,
        "typ": "refresh",
        "jti": jti,
    }
    refresh_token = jwt.encode(refresh_payload, APP_REFRESH_SECRET, algorithm="HS256")

    return access_token, access_exp, refresh_token, refresh_exp


def verify_access(token: str) -> Dict[str, Any]:
    payload = jwt.decode(
        token,
        APP_JWT_SECRET,
        algorithms=["HS256"],
        audience=AUD,
        options={"require": ["exp", "iat", "aud", "iss"]},
    )
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def verify_refresh(token: str) -> Dict[str, Any]:
    payload = jwt.decode(
        token,
        APP_REFRESH_SECRET,
        algorithms=["HS256"],
        audience=AUD,
        options={"require": ["exp", "iat", "aud", "iss"]},
    )
    if payload.get("typ") != "refresh":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def set_refresh_cookie(response, refresh_token: str, refresh_exp_epoch: int) -> None:
    # FastAPI Response.set_cookie signature is compatible
    response.set_cookie(
        key=COOKIE_NAME,
        value=refresh_token,
        path=COOKIE_PATH,
        secure=COOKIE_SECURE,
        httponly=COOKIE_HTTPONLY,
        samesite=COOKIE_SAMESITE,  # "None" for cross-site SPA↔API
        expires=refresh_exp_epoch,  # absolute epoch seconds
    )


def clear_refresh_cookie(response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path=COOKIE_PATH,
        secure=COOKIE_SECURE,
        httponly=COOKIE_HTTPONLY,
        samesite=COOKIE_SAMESITE,
    )
