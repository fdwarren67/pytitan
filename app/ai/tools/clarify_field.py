import json
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from langchain.tools import StructuredTool
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser

_prompt = ChatPromptTemplate.from_template(
    """
    You are a clarification assistant.
    Generate a short, natural question to obtain a missing field value.

    Field name: {field_name}
    Field type: {field_type}
    Description: {description}
    Allowed values: {allowed_values}

    Rules:
    - Be clear and conversational.
    - No technical terms like "enum" or "nullable".
    - If choices are provided, list them exactly and nothing more.
    - Keep the question under 15 words.

    Return JSON only: {{"question":"..."}}
    """
)
_llm = ChatOpenAI(model="gpt-4o-mini")
_parser = JsonOutputParser()
_chain = _prompt | _llm | _parser


def _clarify_field(
    field_name: str,
    field_type: Optional[str],
    description: Optional[str] = None,
    allowed_values: Optional[List[str]] = None,
) -> Dict[str, Any]:
    allowed_str = ", ".join(allowed_values) if allowed_values else "None"
    resp = _chain.invoke(
        {
            "field_name": field_name,
            "field_type": field_type or "string",
            "description": description or "None",
            "allowed_values": allowed_str,
        }
    )
    if isinstance(resp, dict):
        result = resp
    elif hasattr(resp, "content"):
        result = json.loads(resp.content.strip())
    else:
        raise ValueError(f"Unexpected response type: {type(resp)}")

    q = result.get("question") or f"What is the value for {field_name}?"
    # hard cap 15 words
    words = q.strip().split()
    if len(words) > 15:
        q = " ".join(words[:15]).rstrip("?") + "?"
    return {"question": q}


class ClarifyFieldInput(BaseModel):
    field_name: str = Field(..., description="Schema field name.")
    field_type: Optional[str] = Field(
        None, description="JSON type (string, integer, number, boolean, etc.)"
    )
    description: Optional[str] = Field(None, description="Field description.")
    allowed_values: Optional[List[str]] = Field(
        None, description="Enum values if constrained."
    )


ClarifyFieldTool = StructuredTool.from_function(
    func=_clarify_field,
    name="ClarifyField",
    description="Generate a natural clarifying question for a single missing schema field.",
    args_schema=ClarifyFieldInput,
)
