# app/auth/routes.py
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel
from typing import Any, Dict
import jwt

from .myauth import verify_google_id_token 
from .mysession import issue_tokens, verify_refresh, set_refresh_cookie, clear_refresh_cookie

router = APIRouter(prefix="/auth", tags=["auth"])

class ExchangeIn(BaseModel):
    id_token: str

def map_roles(email: str | None) -> list[str]:
    e = (email or "").lower()
    if e in {"alice@acme.com"}: return ["admin"]
    if e.endswith("@acme.com"): return ["analyst"]

    return ["reader"]

@router.post("/exchange")
def exchange(body: ExchangeIn, response: Response):
    claims = verify_google_id_token(body.id_token)
    roles = [] 
    access, access_exp, refresh, refresh_exp = issue_tokens(
        {"sub": claims["sub"], "email": claims.get("email")}, roles
    )
    set_refresh_cookie(response, refresh, refresh_exp)
    return {
        "token_type": "Bearer",
        "access_token": access,
        "expires_in": access_exp - int(__import__("time").time()),
    }

@router.post("/refresh")
def refresh(request: Request, response: Response):
    cookie = request.cookies.get("refresh")  # or your COOKIE_NAME
    if not cookie:
        raise HTTPException(status_code=401, detail="missing refresh cookie")

    payload = verify_refresh(cookie)  # verifies & raises on error

    access, access_exp, refresh_new, refresh_exp = issue_tokens(
        {"sub": payload["sub"], "email": None}, roles=[]
    )
    set_refresh_cookie(response, refresh_new, refresh_exp)
    return {
        "token_type": "Bearer",
        "access_token": access,
        "expires_in": access_exp - int(__import__("time").time()),
    }

@router.post("/logout")
def logout(response: Response):
    clear_refresh_cookie(response)
    return {"ok": True}
