"""
Ontology Generator Manager

Uses an LLM agent with tool-calling to generate OWL ontologies (Turtle)
from database table metadata.  Adapted from OntoBricks.

The agent loop:
  1. Builds a system prompt defining the ontology-engineer role
  2. Sends metadata + guidelines to the LLM
  3. The LLM may call tools (get_metadata / get_table_detail) to inspect schemas
  4. On the final iteration tools are withheld to force a Turtle output
  5. The Turtle is parsed into structured Python dicts via OntologyParser
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.common.config import Settings
from src.common.logging import get_logger
from src.owl.owl_parser import OntologyParser

logger = get_logger(__name__)

MAX_ITERATIONS = 10
_MAX_TABLES_IN_METADATA = 50
_MAX_COLUMNS_PER_TABLE = 80


# =====================================================================
# Data classes
# =====================================================================

@dataclass
class AgentStep:
    """One observable step of the agent's execution."""
    step_type: str          # tool_call | tool_result | output
    content: str
    tool_name: str = ""
    duration_ms: int = 0


@dataclass
class AgentResult:
    """Outcome of a full agent run."""
    success: bool
    owl_content: str = ""
    classes: List[Dict] = field(default_factory=list)
    properties: List[Dict] = field(default_factory=list)
    ontology_info: Dict = field(default_factory=dict)
    constraints: List[Dict] = field(default_factory=list)
    axioms: List[Dict] = field(default_factory=list)
    steps: List[AgentStep] = field(default_factory=list)
    iterations: int = 0
    error: str = ""
    usage: Dict[str, int] = field(default_factory=dict)


# =====================================================================
# System prompt
# =====================================================================

SYSTEM_PROMPT = """\
You are an expert ontology engineer. Your task is to generate a high-quality \
OWL ontology in **Turtle** format.

TOOLS
You have two tools:
  • get_metadata    – get all table schemas (names, columns, types)
  • get_table_detail – get detailed info for one table

WORKFLOW
1. Call get_metadata to understand the database schema.
2. Optionally call get_table_detail for tables that need deeper inspection.
3. Generate the Turtle ontology from all gathered information.

NAMING RULES (CRITICAL – NO EXCEPTIONS)
• Classes: PascalCase (Customer, SalesOrder)
• Properties: lowerCamelCase (hasName, firstName)
• NO spaces, underscores or hyphens in local names.
• Convert: street_address → streetAddress, Sales Order → SalesOrder

PROPERTY TYPES
• owl:DatatypeProperty + xsd:type for attributes (string, integer, date …)
• owl:ObjectProperty for relationships between classes only

RELATIONSHIP RULES
• NEVER create bidirectional relationships.
• Between any two classes A and B create at most ONE ObjectProperty.
• Choose the most natural direction.

CRITICAL OUTPUT RULES:
• When you have gathered enough context, output ONLY valid Turtle syntax.
• Do NOT include any natural language, explanations, or commentary.
• Do NOT wrap in markdown code fences.
• Your ENTIRE response must be valid Turtle starting with @prefix declarations.
• NEVER start with phrases like "Here is", "Now I will", "Based on", etc."""


# =====================================================================
# Metadata tools (adapted from OntoBricks tools/metadata.py)
# =====================================================================

def _tool_get_metadata(metadata: dict, **_kwargs) -> str:
    """Return table metadata, truncated to avoid context overflow."""
    tables = metadata.get("tables", [])
    if not tables:
        return json.dumps({"error": "No metadata loaded", "tables": []})

    total_tables = len(tables)
    tables = tables[:_MAX_TABLES_IN_METADATA]

    result: List[dict] = []
    for t in tables:
        cols = [
            {"name": c.get("name", ""), "type": c.get("type", ""), "comment": c.get("comment", "")}
            for c in (t.get("columns") or [])[:_MAX_COLUMNS_PER_TABLE]
        ]
        total_cols = len(t.get("columns") or [])
        entry: Dict[str, Any] = {
            "name": t.get("name", ""),
            "full_name": t.get("full_name", t.get("name", "")),
            "comment": t.get("comment", ""),
            "columns": cols,
        }
        if total_cols > _MAX_COLUMNS_PER_TABLE:
            entry["columns_truncated"] = True
            entry["total_columns"] = total_cols
        result.append(entry)

    output: Dict[str, Any] = {"tables": result}
    if total_tables > _MAX_TABLES_IN_METADATA:
        output["tables_truncated"] = True
        output["total_tables"] = total_tables
    return json.dumps(output)


def _tool_get_table_detail(metadata: dict, table_name: str = "", **_kwargs) -> str:
    """Return full schema for a single table (no truncation)."""
    if not table_name:
        return json.dumps({"error": "table_name is required"})
    tables = metadata.get("tables", [])
    for t in tables:
        if t.get("name") == table_name or t.get("full_name") == table_name:
            return json.dumps(t)
    return json.dumps({"error": f"Table '{table_name}' not found in metadata"})


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_metadata",
            "description": "Get all table schemas (names, columns, data types, comments). "
                           "Returns a summary of all available tables. Use get_table_detail "
                           "for full schema of a specific table.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_detail",
            "description": "Get the full schema for a specific table including all columns "
                           "with data types and comments. Use when you need complete details "
                           "for a particular table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name or full_name of the table to inspect",
                    }
                },
                "required": ["table_name"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "get_metadata": _tool_get_metadata,
    "get_table_detail": _tool_get_table_detail,
}


# =====================================================================
# Manager
# =====================================================================

class OntologyGeneratorManager:
    """Generates OWL ontologies from metadata using an LLM agent loop."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def _get_openai_client(self, user_token: Optional[str] = None):
        """Create an OpenAI client via the shared factory.

        Args:
            user_token: Per-user OBO token (optional, for Databricks Apps context).
        """
        from src.common.llm_client import create_openai_client

        return create_openai_client(self._settings, user_token=user_token)

    # ------------------------------------------------------------------
    # Agent helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_prompt(
        guidelines: str,
        options: dict,
        base_uri: str,
        selected_tables: List[str],
    ) -> str:
        include_attrs = options.get("includeDataProperties", True)
        include_rels = options.get("includeRelationships", True)
        include_inherit = options.get("includeInheritance", True)

        parts = [f"Base URI: {base_uri}"]
        if selected_tables:
            parts.append(f"Selected tables: {', '.join(selected_tables)}")
        parts.append(
            f"Guidelines: {guidelines or 'Create a domain ontology from the available schema.'}"
        )

        gen = []
        if include_attrs:
            gen.append("DatatypeProperties for attributes")
        if include_rels:
            gen.append("ObjectProperties for relationships")
        if include_inherit:
            gen.append("class hierarchy with rdfs:subClassOf")
        gen.append("rdfs:labels for all elements")
        parts.append(f"Generate OWL with: {', '.join(gen)}.")
        parts.append(
            "Start by using your tools to gather the metadata, "
            "then generate the ontology."
        )
        return "\n".join(parts)

    def _execute_tool(self, metadata: dict, tool_name: str, arguments: dict) -> str:
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            t0 = time.time()
            result = handler(metadata, **arguments)
            elapsed = int((time.time() - t0) * 1000)
            logger.info("Tool '%s' completed in %dms, returned %d chars", tool_name, elapsed, len(result))
            return result
        except Exception as exc:
            logger.exception("Tool '%s' raised exception: %s", tool_name, exc)
            return json.dumps({"error": f"Tool execution failed: {exc}"})

    @staticmethod
    def _extract_turtle(content: str) -> str:
        """Extract Turtle content from LLM output that may contain preamble text.

        LLMs often wrap the actual Turtle in markdown fences or include
        explanatory prose before the ``@prefix`` declarations.  This method
        strips those so the downstream parser receives clean Turtle.
        """

        # Strip markdown code fences (```turtle ... ``` or ``` ... ```)
        fence_match = re.search(r"```(?:turtle|ttl)?\s*\n(.*?)```", content, re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()

        # Find the first @prefix or @base line and discard everything before it
        prefix_idx = content.find("@prefix")
        base_idx = content.find("@base")
        if prefix_idx == -1 and base_idx == -1:
            return content  # no recognisable Turtle directives — return as-is
        if prefix_idx == -1:
            start = base_idx
        elif base_idx == -1:
            start = prefix_idx
        else:
            start = min(prefix_idx, base_idx)

        if start > 0:
            logger.info("Stripped %d chars of preamble text before Turtle content", start)

        return content[start:]

    # ------------------------------------------------------------------
    # Connector helpers
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_tables_from_connector(
        connector,
        selected_paths: List[str],
        *,
        max_depth: int = 5,
        max_tables: int = 200,
    ) -> List[dict]:
        """Walk *selected_paths* via *connector* and return table metadata dicts.

        Container paths (catalogs, schemas) are expanded recursively up to
        *max_depth* levels.  Returns at most *max_tables* tables.

        Args:
            connector: An ``AssetConnector`` instance.
            selected_paths: Paths selected by the user in the schema browser.
            max_depth: Maximum recursion depth for container expansion.
            max_tables: Stop collecting once this many tables are found.

        Returns:
            List of ``{"name", "full_name", "comment", "columns": [...]}`` dicts.
        """
        from src.connectors.base import ListAssetsOptions

        tables_metadata: List[dict] = []
        seen: set = set()

        def _collect(path: str, depth: int = 0):
            if path in seen or len(tables_metadata) >= max_tables:
                return
            seen.add(path)

            if depth > max_depth:
                logger.warning("Max depth %d reached at path %s — skipping", max_depth, path)
                return

            meta = connector.get_asset_metadata(path)
            if meta and meta.schema_info and meta.schema_info.columns:
                cols = [
                    {"name": c.name, "type": c.data_type, "comment": c.description or ""}
                    for c in meta.schema_info.columns
                ]
                tables_metadata.append({
                    "name": meta.name,
                    "full_name": meta.identifier,
                    "comment": meta.description or meta.comment or "",
                    "columns": cols,
                })
                return

            try:
                children = connector.list_containers(parent_path=path)
                for child in children:
                    child_path = child.get("path", "")
                    if child_path:
                        _collect(child_path, depth + 1)
            except Exception:
                pass

            try:
                assets = connector.list_assets(ListAssetsOptions(path=path, limit=200))
                for asset in assets:
                    _collect(asset.identifier, depth + 1)
            except Exception:
                pass

        for p in selected_paths:
            _collect(p)

        return tables_metadata

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_ontology(
        self,
        metadata: dict,
        guidelines: str = "",
        options: Optional[dict] = None,
        base_uri: str = "http://ontos.example.org/ontology#",
        selected_tables: Optional[List[str]] = None,
        on_step: Optional[Callable[[str], None]] = None,
        user_token: Optional[str] = None,
    ) -> AgentResult:
        """Run the ontology-generation agent.

        Args:
            metadata: {"tables": [{"name": ..., "columns": [...]}]}
            guidelines: Free-text instructions for the LLM
            options: Generation toggles (includeDataProperties, includeRelationships, includeInheritance)
            base_uri: Base URI for generated ontology
            selected_tables: Subset of table names to use (None = all)
            on_step: Optional progress callback
            user_token: Per-user OBO token for Databricks Apps context

        Returns:
            AgentResult with OWL content and parsed structures
        """
        if not self._settings.LLM_ENABLED:
            return AgentResult(success=False, error="LLM functionality is disabled (LLM_ENABLED=false)")

        endpoint = self._settings.LLM_ENDPOINT
        if not endpoint:
            return AgentResult(success=False, error="No LLM endpoint configured (LLM_ENDPOINT)")

        options = options or {}
        result = AgentResult(success=False)

        # Filter to selected tables if specified
        working_metadata = metadata
        if selected_tables and metadata.get("tables"):
            filtered = [
                t for t in metadata["tables"]
                if (t.get("full_name") or t.get("name")) in selected_tables
            ]
            if filtered:
                working_metadata = {**metadata, "tables": filtered}
                logger.info("Filtered metadata to %d/%d selected tables", len(filtered), len(metadata["tables"]))

        user_prompt = self._build_user_prompt(
            guidelines=guidelines,
            options=options,
            base_uri=base_uri,
            selected_tables=selected_tables or [],
        )

        messages: List[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        total_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0}

        def notify(msg: str):
            if on_step:
                on_step(msg)

        notify("Starting ontology generation agent…")
        logger.info("Agent start — endpoint=%s, tables=%d, max_iterations=%d",
                     endpoint, len(working_metadata.get("tables", [])), MAX_ITERATIONS)

        try:
            client = self._get_openai_client(user_token=user_token)
        except Exception as exc:
            result.error = f"Failed to connect to LLM: {exc}"
            logger.error("Agent: %s", result.error)
            return result

        tools_supported = True

        for iteration in range(MAX_ITERATIONS):
            logger.info("Iteration %d/%d — %d messages", iteration + 1, MAX_ITERATIONS, len(messages))
            notify(f"Agent thinking… (step {iteration + 1})")

            is_last = iteration >= MAX_ITERATIONS - 1
            send_tools = TOOL_DEFINITIONS if (tools_supported and not is_last) else None

            t0 = time.time()
            try:
                kwargs: Dict[str, Any] = {
                    "model": endpoint,
                    "messages": messages,
                    "max_tokens": 4096,
                    "temperature": 0.1,
                }
                if send_tools:
                    kwargs["tools"] = send_tools
                    kwargs["tool_choice"] = "auto"

                # chat_completion retries without `temperature` if the endpoint
                # rejects it (databricks-claude-opus-4-x).
                from src.common.llm_client import chat_completion
                response = chat_completion(client, **kwargs)
            except Exception as exc:
                exc_str = str(exc)
                # If the endpoint rejected tools, fall back to direct mode
                if tools_supported and ("400" in exc_str or "422" in exc_str or "tool" in exc_str.lower()):
                    logger.warning("Endpoint rejected tools — falling back to direct mode")
                    tools_supported = False
                    notify("Endpoint does not support tools — using direct generation…")
                    try:
                        from src.common.llm_client import chat_completion
                        response = chat_completion(
                            client,
                            model=endpoint,
                            messages=messages,
                            max_tokens=4096,
                            temperature=0.1,
                        )
                    except Exception as inner:
                        result.error = f"LLM request failed: {inner}"
                        logger.error("Agent: fallback also failed: %s", inner)
                        return result
                else:
                    result.error = f"LLM request failed: {exc}"
                    logger.error("Agent: LLM request failed at iteration %d: %s", iteration + 1, exc)
                    return result

            elapsed_ms = int((time.time() - t0) * 1000)
            logger.info("Iteration %d: LLM responded in %dms", iteration + 1, elapsed_ms)

            usage = response.usage
            if usage:
                total_usage["prompt_tokens"] += usage.prompt_tokens or 0
                total_usage["completion_tokens"] += usage.completion_tokens or 0

            assistant_message = response.choices[0].message

            if assistant_message.tool_calls:
                logger.info("Iteration %d: %d tool call(s)", iteration + 1, len(assistant_message.tool_calls))

                # Append the assistant message (with tool_calls) to conversation
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in assistant_message.tool_calls
                    ],
                })

                for tc in assistant_message.tool_calls:
                    tool_name = tc.function.name
                    try:
                        arguments = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except json.JSONDecodeError:
                        arguments = {}

                    notify(f"Calling {tool_name}…")
                    result.steps.append(AgentStep(step_type="tool_call", content=json.dumps(arguments), tool_name=tool_name))

                    t1 = time.time()
                    tool_result = self._execute_tool(working_metadata, tool_name, arguments)
                    tool_ms = int((time.time() - t1) * 1000)

                    result.steps.append(AgentStep(
                        step_type="tool_result",
                        content=(tool_result[:500] + "…") if len(tool_result) > 500 else tool_result,
                        tool_name=tool_name,
                        duration_ms=tool_ms,
                    ))

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    })
            else:
                # Agent produced a text response — should be Turtle
                content = assistant_message.content or ""

                # Strip preamble text that LLMs often include before the actual Turtle
                content = self._extract_turtle(content)

                starts_with_prefix = content.strip().startswith("@prefix")
                logger.info("Iteration %d: final text output — %d chars, starts_with_@prefix=%s",
                            iteration + 1, len(content), starts_with_prefix)

                result.steps.append(AgentStep(
                    step_type="output",
                    content=(content[:200] + "…") if len(content) > 200 else content,
                    duration_ms=elapsed_ms,
                ))

                result.success = True
                result.owl_content = content
                result.iterations = iteration + 1
                result.usage = total_usage

                # Parse the generated Turtle into structured data
                try:
                    parser = OntologyParser(content)
                    result.classes = parser.get_classes()
                    result.properties = parser.get_properties()
                    result.ontology_info = parser.get_ontology_info()
                    result.constraints = parser.get_constraints()
                    result.axioms = parser.get_axioms()
                    logger.info("Parsed ontology: %d classes, %d properties",
                                len(result.classes), len(result.properties))
                except Exception as parse_exc:
                    logger.warning("Failed to parse generated Turtle: %s", parse_exc)
                    result.error = f"Generated content could not be parsed: {parse_exc}"

                notify("Agent completed!")
                return result

        result.error = f"Agent reached maximum iterations ({MAX_ITERATIONS}) without producing output"
        logger.error("Agent failed: %s", result.error)
        return result
