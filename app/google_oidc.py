import os
from functools import lru_cache
from typing import Dict, Any, List, Set

import os, logging, httpx, jwt
from fastapi import Security, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient

log = logging.getLogger("auth")

GOOGLE_ISS = "https://accounts.google.com"
DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")  

bearer = HTTPBearer(auto_error=True)

@lru_cache(maxsize=1)
def _discovery():
    with httpx.Client(timeout=5) as c:
        r = c.get(DISCOVERY_URL); r.raise_for_status(); return r.json()

JWKS_URI = _discovery()["jwks_uri"]
jwks_client = PyJWKClient(JWKS_URI)
ALGS = ("RS256",)

def verify_google_id_token(
    credentials: HTTPAuthorizationCredentials = Security(bearer),
):
    token = credentials.credentials
    try:
        # Quick sanity: header & payload (no signature check yet)
        hdr = jwt.get_unverified_header(token)
        body = jwt.decode(token, options={"verify_signature": False})
        if body.get("iss") != GOOGLE_ISS:
            log.warning("Bad iss: %s", body.get("iss"))
            raise HTTPException(status_code=401, detail="Bad issuer")
        aud = body.get("aud")
        if GOOGLE_CLIENT_ID and aud != GOOGLE_CLIENT_ID:
            log.warning("Bad aud: %s (expected %s)", aud, GOOGLE_CLIENT_ID)
            raise HTTPException(status_code=401, detail="Bad audience")

        # Signature verification
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGS,
            audience=GOOGLE_CLIENT_ID,
            issuer=GOOGLE_ISS,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )

        if not claims.get("email_verified", False):
            raise HTTPException(status_code=401, detail="Email not verified")
        return claims

    except HTTPException:
        raise
    except Exception as e:
        log.exception("Token verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# Simple role mapping example (replace with DB-based lookup)
def _roles_for(claims: Dict[str, Any]) -> Set[str]:
    email = (claims.get("email") or "").lower()
    by_email = {
        "fdwarren@gmail.com": {"admin", "read:data"}
    }
    return by_email.get(email, set())

def require_roles(required: List[str]):
    def _dep(claims: Dict[str, Any] = Depends(verify_google_id_token)):
        have = _roles_for(claims)
        if not set(required).issubset(have):
            raise HTTPException(status_code=403, detail="Forbidden: missing role")
        return claims
    return _dep
