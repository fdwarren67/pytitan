import json
from typing import Dict, Any, List
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field


def build_schema_options(schema_library: Dict[str, Any]) -> List[Dict[str, Any]]:
    options = []
    for name, sch in list(schema_library.items()):
        options.append({"schema": name, "description": sch.get("description", "")})
    return options


prompt = ChatPromptTemplate.from_template(
    """
    You are a data extraction assistant.
    Task: choose the best schema from the options and extract fields mentioned by the user.

    --- Schema Options (name + descriptions) ---
    {schema_options}

    --- User Input ---
    {user_input}

    Instructions:
    1) Return valid JSON with exactly one key:
       - "schema": the chosen schema name from the options (string or null).
    2) If unsure which schema applies, set "schema" to null.
    4) Do not invent values. Omit fields not present in input.
    5) JSON only. No explanations.

    Examples:
    Example A → user mentions blogging
    {{ "schema": "BlogPost" }}

    Example B → unclear
    {{ "schema": null }}
    """
)

llm = ChatOpenAI(model="gpt-4o-mini")
parser = JsonOutputParser()
chain = prompt | llm | parser


def extract_candidate_json(user_input: str, schema_library: dict) -> dict:
    options = build_schema_options(schema_library)
    resp = chain.invoke(
        {
            "schema_options": json.dumps(options, ensure_ascii=False),
            "user_input": user_input,
        }
    )

    if isinstance(resp, dict):
        result = resp
    elif hasattr(resp, "content"):
        result = json.loads(resp.content.strip())
    else:
        raise ValueError(f"Unexpected response type: {type(resp)}")

    result.setdefault("schema", None)
    result.setdefault("data", {})
    if not isinstance(result["data"], dict):
        result["data"] = {}

    return result


class InferSchemaInput(BaseModel):
    user_input: str = Field(..., description="Natural language reference to a schema.")
    schema_library: dict = Field(..., description="Schema library for reference.")


InferSchemaTool = StructuredTool.from_function(
    func=extract_candidate_json,
    name="InferSchema",
    description="Infer the best matching schema from the library and extract structured data from the user input.",
    args_schema=InferSchemaInput,
)
