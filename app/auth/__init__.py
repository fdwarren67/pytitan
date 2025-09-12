"""
Authentication module for the Pytitan data service.

This module handles Google OAuth authentication and JWT token verification.
"""

from .oauth import (
    verify_google_id_token,
    _roles_for,
    require_roles,
)

__all__ = [
    "verify_google_id_token",
    "_roles_for",
    "require_roles",
]
