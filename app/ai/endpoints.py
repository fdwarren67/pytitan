"""
FastAPI endpoints for AI functionality.
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel

from .service import AIService
from ..auth.require import require_auth, require_roles_access


router = APIRouter(prefix="/ai", tags=["AI"])

# Initialize AI service
ai_service = AIService()


class ProcessInputRequest(BaseModel):
    """Request model for processing natural language input."""

    input_text: str
    schema_name: Optional[str] = None
    session_id: Optional[str] = None


class ClarifyRequest(BaseModel):
    """Request model for providing clarification."""

    clarification: str
    session_id: str


class ConversationRequest(BaseModel):
    """Request model for conversation management."""

    session_id: str


@router.get("/schemas", dependencies=[Depends(require_roles_access(["read:data"]))])
def get_available_schemas():
    """Get list of available AI processing schemas."""
    try:
        schemas = ai_service.get_available_schemas()
        return {"schemas": schemas, "count": len(schemas)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading schemas: {str(e)}")


@router.get(
    "/schemas/{schema_name}",
    dependencies=[Depends(require_roles_access(["read:data"]))],
)
def get_schema_definition(schema_name: str):
    """Get the full definition of a specific schema."""
    try:
        schema_def = ai_service.get_schema_definition(schema_name)
        if not schema_def:
            raise HTTPException(
                status_code=404, detail=f"Schema '{schema_name}' not found"
            )
        return {"schema_name": schema_name, "definition": schema_def}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading schema: {str(e)}")


@router.post("/process", dependencies=[Depends(require_roles_access(["read:data"]))])
def process_input(
    request: ProcessInputRequest = Body(
        ..., description="Natural language input to process"
    ),
    claims: dict = Depends(require_auth),
):
    """
    Process natural language input and extract structured data using AI.

    This endpoint:
    1. Analyzes the input text
    2. Infers the appropriate schema (or uses the specified one)
    3. Extracts structured data using AI
    4. Validates the extracted data
    5. Returns the result or asks for clarification
    6. Maintains conversation context using session_id
    """
    try:
        result = ai_service.process_input(
            user_input=request.input_text,
            schema_name=request.schema_name,
            session_id=request.session_id,
        )

        return {
            "input": request.input_text,
            "schema_name": request.schema_name,
            "session_id": result.get("session_id"),
            "result": result,
            "processed_by": claims.get("email", "unknown"),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing input: {str(e)}")


@router.post("/clarify", dependencies=[Depends(require_roles_access(["read:data"]))])
def clarify_fields(
    request: ClarifyRequest = Body(
        ..., description="Clarification for validation errors"
    ),
    claims: dict = Depends(require_auth),
):
    """
    Provide clarification for validation errors from a previous processing request.
    Uses session_id to maintain conversation context.
    """
    try:
        result = ai_service.clarify_fields(
            clarification=request.clarification, session_id=request.session_id
        )

        return {
            "clarification": request.clarification,
            "session_id": request.session_id,
            "result": result,
            "processed_by": claims.get("email", "unknown"),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error processing clarification: {str(e)}"
        )


@router.post(
    "/process-simple", dependencies=[Depends(require_roles_access(["read:data"]))]
)
def process_input_simple(
    input_text: str = Body(..., description="Natural language input to process"),
    schema_name: Optional[str] = Body(
        None, description="Optional specific schema to use"
    ),
    claims: dict = Depends(require_auth),
):
    """
    Simplified endpoint for processing input with just text and optional schema.
    """
    try:
        result = ai_service.process_input(
            user_input=input_text, schema_name=schema_name
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing input: {str(e)}")


@router.get("/health", dependencies=[Depends(require_roles_access(["read:data"]))])
def ai_health_check():
    """Health check for AI service."""
    try:
        schemas = ai_service.get_available_schemas()
        return {
            "status": "healthy",
            "schemas_loaded": len(schemas),
            "service": "AI Processing",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI service unhealthy: {str(e)}")


@router.get(
    "/conversation/{session_id}",
    dependencies=[Depends(require_roles_access(["read:data"]))],
)
def get_conversation_history(session_id: str, claims: dict = Depends(require_auth)):
    """
    Get conversation history for a specific session.
    """
    try:
        history = ai_service.get_conversation_history(session_id)
        if history is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return {
            "session_id": session_id,
            "conversation": history,
            "retrieved_by": claims.get("email", "unknown"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving conversation: {str(e)}"
        )


@router.delete(
    "/conversation/{session_id}",
    dependencies=[Depends(require_roles_access(["read:data"]))],
)
def clear_conversation(session_id: str, claims: dict = Depends(require_auth)):
    """
    Clear conversation history for a specific session.
    """
    try:
        success = ai_service.clear_conversation(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return {
            "session_id": session_id,
            "message": "Conversation cleared successfully",
            "cleared_by": claims.get("email", "unknown"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error clearing conversation: {str(e)}"
        )
