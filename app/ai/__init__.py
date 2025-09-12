"""
AI module for the Pytitan data service.

This module provides AI-powered data processing capabilities including
schema inference, data hydration, and validation.

Structure:
- endpoints.py: FastAPI endpoints for AI functionality
- service.py: AI processing service
- tools/: AI processing tools
- utils/: Schema utilities
- workflow/: LangGraph workflow orchestration
"""

from .endpoints import router
from .service import AIService

__all__ = [
    "router",
    "AIService",
]
