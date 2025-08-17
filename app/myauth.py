from typing import Dict, Any, List, Set

import os, logging, httpx, jwt
from fastapi import Security, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient

log = logging.getLogger("auth")

ACCEPTED_ISS = ("accounts.google.com", "https://accounts.google.com")
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")  
ALGS = ("RS256",)

jwks_client = PyJWKClient(JWKS_URL)

bearer = HTTPBearer(auto_error=False)

def verify_google_id_token(token: str) -> dict:
    try:
        # Quick sanity (no signature): check iss/aud early
        body = jwt.decode(token, options={"verify_signature": False})
        iss = body.get("iss")
        if iss not in ACCEPTED_ISS:
            log.warning("Bad iss: %s", iss)
            raise HTTPException(status_code=401, detail="Bad issuer")

        aud = body.get("aud")
        if GOOGLE_CLIENT_ID and aud != GOOGLE_CLIENT_ID:
            log.warning("Bad aud: %s (expected %s)", aud, GOOGLE_CLIENT_ID)
            raise HTTPException(status_code=401, detail="Bad audience")

        # Signature verification against Google JWKS
        signing_key = jwks_client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=ALGS,
            audience=GOOGLE_CLIENT_ID,
            issuer=ACCEPTED_ISS,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )

        if not claims.get("email_verified", False):
            raise HTTPException(status_code=401, detail="Email not verified")
        return claims

    except HTTPException:
        raise
    except Exception as e:
        log.exception("Google ID token verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid or expired token")

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
