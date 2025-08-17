from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .mysession import verify_access

bearer = HTTPBearer(auto_error=False)

def require_auth(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        return verify_access(creds.credentials)  # returns payload with sub/email/roles
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
