# app/auth/routes.py
import time
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel
from typing import Any, Dict
import jwt

from ..auth import verify_google_id_token
from ..session import (
    issue_tokens,
    verify_refresh,
    set_refresh_cookie,
    clear_refresh_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class ExchangeIn(BaseModel):
    id_token: str


def map_roles(email: str | None) -> list[str]:
    # e = (email or "").lower()
    # if e in {"fdwarren@gmail.com"}: return ["admin"]
    # if e.endswith("@acme.com"): return ["analyst"]

    return ["read:data"]


@router.post("/exchange")
def exchange(body: ExchangeIn, response: Response):
    claims = verify_google_id_token(body.id_token)
    roles = map_roles(claims.get("email"))

    access, access_exp, refresh, refresh_exp = issue_tokens(
        {"sub": claims["sub"], "email": claims.get("email")}, roles
    )
    set_refresh_cookie(response, refresh, refresh_exp)
    return {
        "token_type": "Bearer",
        "access_token": access,
        "expires_in": access_exp - int(time.time()),
    }


@router.post("/refresh")
def refresh(request: Request, response: Response):
    cookie = request.cookies.get("refresh")
    if not cookie:
        raise HTTPException(status_code=401, detail="missing refresh cookie")

    payload = verify_refresh(cookie)  # has sub/email/roles
    user = {"sub": payload["sub"], "email": payload.get("email")}
    roles = payload.get("roles", [])

    access, access_exp, refresh_new, refresh_exp = issue_tokens(user, roles)
    set_refresh_cookie(response, refresh_new, refresh_exp)
    return {
        "token_type": "Bearer",
        "access_token": access,
        "expires_in": access_exp - int(time.time()),
    }


@router.post("/logout")
def logout(response: Response):
    clear_refresh_cookie(response)
    return {"ok": True}
