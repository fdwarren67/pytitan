"""
AI Service for processing natural language input and extracting structured data.
"""

import os
import uuid
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime, timedelta

from .utils import load_schemas
from .workflow import State, resolve_schema_name, create_app, handle_validation_errors


class ConversationState:
    """Represents the state of a conversation session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.utcnow()
        self.last_updated = datetime.utcnow()
        self.messages: List[Dict[str, Any]] = []
        self.current_schema: Optional[str] = None
        self.partial_object: Dict[str, Any] = {}
        self.validation_errors: List[Dict[str, Any]] = []
        self.context: Dict[str, Any] = {}

    def add_message(
        self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None
    ):
        """Add a message to the conversation history."""
        self.messages.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": metadata or {},
            }
        )
        self.last_updated = datetime.utcnow()

    def is_expired(self, max_age_hours: int = 24) -> bool:
        """Check if the conversation has expired."""
        return datetime.utcnow() - self.created_at > timedelta(hours=max_age_hours)

    def to_dict(self) -> Dict[str, Any]:
        """Convert conversation state to dictionary."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "messages": self.messages,
            "current_schema": self.current_schema,
            "partial_object": self.partial_object,
            "validation_errors": self.validation_errors,
            "context": self.context,
        }


class AIService:
    """Service for AI-powered data processing with conversation memory."""

    def __init__(self):
        self.schema_library = load_schemas("app/ai/schemas")
        self.app = create_app()
        self.conversations: Dict[str, ConversationState] = {}

    def get_available_schemas(self) -> List[str]:
        """Get list of available schema names."""
        return list(self.schema_library.keys())

    def get_schema_definition(self, schema_name: str) -> Optional[Dict[str, Any]]:
        """Get the full schema definition for a given schema name."""
        return self.schema_library.get(schema_name)

    def _cleanup_expired_conversations(self):
        """Remove expired conversations to prevent memory leaks."""
        expired_sessions = [
            session_id
            for session_id, conv in self.conversations.items()
            if conv.is_expired()
        ]
        for session_id in expired_sessions:
            del self.conversations[session_id]

    def _get_or_create_conversation(
        self, session_id: Optional[str] = None
    ) -> ConversationState:
        """Get existing conversation or create a new one."""
        self._cleanup_expired_conversations()

        if not session_id:
            session_id = str(uuid.uuid4())

        if session_id not in self.conversations:
            self.conversations[session_id] = ConversationState(session_id)

        return self.conversations[session_id]

    def get_conversation_history(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the conversation history for a session."""
        if session_id in self.conversations:
            return self.conversations[session_id].to_dict()
        return None

    def clear_conversation(self, session_id: str) -> bool:
        """Clear a conversation session."""
        if session_id in self.conversations:
            del self.conversations[session_id]
            return True
        return False

    def _build_contextual_input(
        self, user_input: str, conversation: ConversationState
    ) -> str:
        """Build contextual input by incorporating conversation history."""
        if not conversation.messages:
            return user_input

        # Get recent messages (last 5 to avoid token limits)
        recent_messages = conversation.messages[-5:]

        # Build context from conversation history
        context_parts = []

        # Add schema context if available
        if conversation.current_schema:
            context_parts.append(f"Current schema: {conversation.current_schema}")

        # Add partial object context if available
        if conversation.partial_object:
            context_parts.append(
                f"Partial object so far: {conversation.partial_object}"
            )

        # Add recent conversation history
        if recent_messages:
            context_parts.append("Recent conversation:")
            for msg in recent_messages:
                role = msg["role"]
                content = msg["content"]
                context_parts.append(f"{role}: {content}")

        # Combine context with current input
        if context_parts:
            context = "\n".join(context_parts)
            return f"Context:\n{context}\n\nCurrent input: {user_input}"

        return user_input

    def process_input(
        self,
        user_input: str,
        schema_name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process natural language input and extract structured data with conversation context.

        Args:
            user_input: Natural language input to process
            schema_name: Optional specific schema to use
            session_id: Optional session ID for conversation continuity

        Returns:
            Dictionary containing the processing result
        """
        # Get or create conversation
        conversation = self._get_or_create_conversation(session_id)

        # Add user message to conversation history
        conversation.add_message("user", user_input, {"schema_name": schema_name})

        # Use schema from conversation context if available and not overridden
        if not schema_name and conversation.current_schema:
            schema_name = conversation.current_schema

        # Build context from conversation history
        context_input = self._build_contextual_input(user_input, conversation)

        # Create initial state with context and existing data
        existing_data = conversation.partial_object or {}
        state = State(
            schema_library=self.schema_library,
            user_input=context_input,
            data=existing_data,
            schema_name=conversation.current_schema,
            schema_def=(
                self.schema_library.get(conversation.current_schema)
                if conversation.current_schema
                else None
            ),
        )

        # If schema is specified, use it directly
        if schema_name:
            schema_def = self.schema_library.get(schema_name)
            if schema_def:
                state.schema_name = schema_name
                state.schema_def = schema_def
                conversation.current_schema = schema_name
            else:
                error_result = {
                    "error": f"Schema '{schema_name}' not found",
                    "available_schemas": self.get_available_schemas(),
                    "session_id": conversation.session_id,
                }
                conversation.add_message(
                    "assistant", f"Schema '{schema_name}' not found", error_result
                )
                return error_result

        # Process through the AI workflow
        result = self.app.run(state)

        # Handle case where schema couldn't be inferred
        if not result.get("schema_name"):
            error_result = {
                "error": "Could not infer schema from input",
                "available_schemas": self.get_available_schemas(),
                "suggestion": "Please specify a schema_name or provide more specific input",
                "session_id": conversation.session_id,
            }
            conversation.add_message(
                "assistant", "Could not infer schema from input", error_result
            )
            return error_result

        # Store the initial partial object and schema
        conversation.partial_object = result.get("data", {})
        conversation.current_schema = result.get("schema_name")

        # Start the validation loop
        return self._validation_loop(conversation)

    def _validation_loop(self, conversation: ConversationState) -> Dict[str, Any]:
        """
        Validation loop that continues until all required fields are populated.
        
        Steps:
        1. Validate current object against schema
        2. If validation passes → return success
        3. If validation fails → ask for first missing field
        4. Wait for user clarification (handled by clarify_fields)
        """
        schema_def = self.schema_library.get(conversation.current_schema)
        if not schema_def:
            return {
                "error": f"Schema '{conversation.current_schema}' not found",
                "session_id": conversation.session_id,
            }
        

        # Validate the current partial object
        from .tools.validate_object import build_model_from_schema, validate_with_clarification
        
        model_cls = build_model_from_schema(conversation.current_schema, schema_def)
        validation_result = validate_with_clarification(model_cls, schema_def, conversation.partial_object, conversation.current_schema)
        
        if validation_result.get("valid"):
            # All required fields are present - success!
            success_result = {
                "status": "success",
                "schema_name": conversation.current_schema,
                "object": conversation.partial_object,
                "message": "Data successfully extracted and validated",
                "session_id": conversation.session_id,
            }
            conversation.add_message(
                "assistant", "Data successfully extracted and validated", success_result
            )
            # Clear validation errors since we're done
            conversation.validation_errors = []
            return success_result
        else:
            # Validation failed - need clarification for missing fields
            missing_fields = validation_result.get("missing", [])
            # Ensure field types are properly set
            for field_error in missing_fields:
                field_name = field_error["field"]
                # Set field types based on common field names
                if field_name in ["username", "email", "fullName", "location", "alignment"]:
                    field_error["field_type"] = "string"
                elif field_name in ["age", "count"]:
                    field_error["field_type"] = "integer"
                elif field_name in ["spacing"]:
                    field_error["field_type"] = "number"
                else:
                    field_error["field_type"] = "string"  # Default to string
            conversation.validation_errors = missing_fields
            
            if missing_fields:
                field = missing_fields[0]["field"]
                spec = schema_def.get("properties", {}).get(field, {})
                expected_type = spec.get("type")
                enum_values = spec.get("enum")

                # Generate clarification question
                from .tools import ClarifyFieldTool

                q = ClarifyFieldTool.invoke(
                    {
                        "field_name": field,
                        "field_type": expected_type,
                        "description": spec.get("description"),
                        "allowed_values": enum_values,
                    }
                )["question"]

                clarification_result = {
                    "status": "validation_errors",
                    "schema_name": conversation.current_schema,
                    "validation_errors": missing_fields,
                    "object": conversation.partial_object,
                    "partial_object": conversation.partial_object,  # Keep both for compatibility
                    "clarification_question": q,
                    "missing_field": field,
                    "field_type": expected_type,
                    "enum_values": enum_values,
                    "message": "Please provide clarification for the validation errors",
                    "session_id": conversation.session_id,
                }
                conversation.add_message("assistant", q, clarification_result)
                return clarification_result
            else:
                # No missing fields but validation still failed - unexpected
                error_result = {
                    "status": "validation_failed",
                    "schema_name": conversation.current_schema,
                    "validation_errors": [],
                    "partial_object": conversation.partial_object,
                    "message": "Validation failed for unknown reasons",
                    "session_id": conversation.session_id,
                }
                conversation.add_message("assistant", "Validation failed for unknown reasons", error_result)
                return error_result

    def clarify_fields(self, clarification: str, session_id: str) -> Dict[str, Any]:
        """
        Process clarification for validation errors and continue the validation loop.

        Args:
            clarification: User's clarification response
            session_id: Session ID to retrieve conversation context

        Returns:
            Updated processing result
        """
        if session_id not in self.conversations:
            return {
                "error": "Session not found",
                "message": "No active conversation found for this session",
            }

        conversation = self.conversations[session_id]

        # Add clarification to conversation history
        conversation.add_message("user", clarification, {"type": "clarification"})

        # Get the missing field from validation errors
        if not conversation.validation_errors:
            return {
                "error": "No validation errors found",
                "message": "No pending validation errors to clarify",
            }

        missing_field = conversation.validation_errors[0]["field"]
        field_type = conversation.validation_errors[0].get("field_type", "string")
        
        # Ensure field type is set correctly
        if field_type == "unknown" or not field_type:
            if missing_field in ["username", "email", "fullName", "location", "alignment"]:
                field_type = "string"
            elif missing_field in ["age", "count"]:
                field_type = "integer"
            elif missing_field in ["spacing"]:
                field_type = "number"
            else:
                field_type = "string"  # Default to string

        # Process the clarification based on field type
        processed_value = self._process_clarification_value(clarification, field_type)

        # Update the partial object with the clarified value
        conversation.partial_object[missing_field] = processed_value

        # Remove the resolved validation error
        conversation.validation_errors.pop(0)

        # Continue the validation loop with the updated object
        return self._validation_loop(conversation)

    def _process_clarification_value(self, clarification: str, field_type: str) -> Any:
        """Process clarification value based on field type."""
        if field_type == "integer":
            try:
                return int(clarification)
            except ValueError:
                return clarification
        elif field_type == "number":
            try:
                return float(clarification)
            except ValueError:
                return clarification
        elif field_type == "boolean":
            return clarification.lower() in ["true", "yes", "1", "y"]
        else:
            return clarification
