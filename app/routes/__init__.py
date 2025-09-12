"""
API routes for the Pytitan data service.

This module provides authentication and public API routes.
"""

from .auth_routes import router

__all__ = [
    "router",
]
