from typing import Dict, Any, Optional
from .state import State
from .nodes import infer_schema, hydrate_object, validate_object


class WorkflowRunner:
    """Custom workflow runner to replace LangGraph orchestration."""

    def __init__(self):
        self.nodes = {
            "infer_schema": infer_schema,
            "hydrate_object": hydrate_object,
            "validate_object": validate_object,
        }

    def run(self, initial_state: State) -> Dict[str, Any]:
        """Run the workflow with the given initial state."""
        state = initial_state
        current_node = "infer_schema"

        while current_node:
            # Execute current node
            updates = self.nodes[current_node](state)

            # Update state with the returned updates
            state_dict = state.model_dump()
            state_dict.update(updates)
            state = State(**state_dict)

            # Route to next node based on current state
            if current_node == "infer_schema":
                # If schema was inferred successfully, go to hydrate_object
                # Otherwise, end the workflow (schema inference failed)
                current_node = "hydrate_object" if state.schema_name else None
            elif current_node == "hydrate_object":
                # Always go to validate_object after hydration
                current_node = "validate_object"
            elif current_node == "validate_object":
                # Always end workflow after validation
                # Let the service handle the validation loop and clarification
                current_node = None

        return state.model_dump()


def create_app():
    """Create and configure the custom workflow application."""
    return WorkflowRunner()
