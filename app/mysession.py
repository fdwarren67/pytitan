import os, time, secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple
import jwt  # PyJWT

APP_JWT_SECRET = os.environ["APP_JWT_SECRET"]
APP_REFRESH_SECRET = os.environ["APP_REFRESH_SECRET"]

ISS = os.getenv("APP_JWT_ISS", "https://data-service")
AUD = os.getenv("APP_JWT_AUD", "data-service")

# Lifetimes
ACCESS_TTL = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "900"))         # 15 min
REFRESH_TTL = int(os.getenv("REFRESH_TOKEN_TTL_SECONDS", "2592000"))   # 30 days

# Cookie settings
COOKIE_NAME   = os.getenv("REFRESH_COOKIE_NAME", "refresh")
COOKIE_PATH   = os.getenv("REFRESH_COOKIE_PATH", "/auth/refresh")
COOKIE_SAMESITE = os.getenv("REFRESH_COOKIE_SAMESITE", "None")
COOKIE_SECURE   = os.getenv("REFRESH_COOKIE_SECURE", "true").lower() == "true"
COOKIE_HTTPONLY = os.getenv("REFRESH_COOKIE_HTTPONLY", "true").lower() == "true"

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _exp(seconds: int) -> datetime:
    return _now() + timedelta(seconds=seconds)

def issue_tokens(user: Dict[str, Any], roles: list[str]) -> Tuple[str, int, str, int]:
    """
    Returns: access_token, access_exp (epoch), refresh_token, refresh_exp (epoch)
    """
    iat = int(time.time())
    access_exp = iat + ACCESS_TTL
    refresh_exp = iat + REFRESH_TTL

    access_payload = {
        "iss": ISS, "aud": AUD, "iat": iat, "exp": access_exp,
        "sub": user["sub"], "email": user.get("email"), "roles": roles, "typ": "access"
    }
    access_token = jwt.encode(access_payload, APP_JWT_SECRET, algorithm="HS256")

    jti = secrets.token_urlsafe(24)
    refresh_payload = {
        "iss": ISS, "aud": AUD, "iat": iat, "exp": refresh_exp, "sub": user["sub"],
        "typ": "refresh", "jti": jti
    }
    refresh_token = jwt.encode(refresh_payload, APP_REFRESH_SECRET, algorithm="HS256")

    return access_token, access_exp, refresh_token, refresh_exp

def verify_access(token: str) -> Dict[str, Any]:
    payload = jwt.decode(token, APP_JWT_SECRET, algorithms=["HS256"], audience=AUD, options={"require": ["exp","iat","aud","iss"]})
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload

def verify_refresh(token: str) -> Dict[str, Any]:
    payload = jwt.decode(token, APP_REFRESH_SECRET, algorithms=["HS256"], audience=AUD, options={"require": ["exp","iat","aud","iss"]})
    if payload.get("typ") != "refresh":
        raise jwt.InvalidTokenError("wrong token type")
    return payload

def set_refresh_cookie(response, refresh_token: str, refresh_exp_epoch: int):
    response.set_cookie(
        key=COOKIE_NAME,
        value=refresh_token,
        path=COOKIE_PATH,
        secure=COOKIE_SECURE,
        httponly=COOKIE_HTTPONLY,
        samesite=COOKIE_SAMESITE,   # "None" for cross-site SPA→API
        expires=refresh_exp_epoch,  # absolute expiry (epoch seconds)
    )

def clear_refresh_cookie(response):
    response.delete_cookie(
        key=COOKIE_NAME,
        path=COOKIE_PATH,
        secure=COOKIE_SECURE,
        httponly=COOKIE_HTTPONLY,
        samesite=COOKIE_SAMESITE,
    )
