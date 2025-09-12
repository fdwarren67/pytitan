from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from ..session import verify_access

bearer = HTTPBearer(auto_error=False)


def require_auth(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        return verify_access(creds.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_roles_access(required: list[str]):
    def _dep(claims=Depends(require_auth)):
        have = set(claims.get("roles", []))
        if not set(required).issubset(have):
            raise HTTPException(status_code=403, detail="Forbidden: missing role")
        return claims

    return _dep
