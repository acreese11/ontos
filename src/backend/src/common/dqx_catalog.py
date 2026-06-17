"""DQX check catalog + ODCS-quality envelope.

Single source of truth for turning a chosen DQX check (a built-in check function
+ arguments, or a raw ``sql_expression``) into the ODCS *explicit-rule* shape that
DQX's ``DataContractRulesGenerator`` executes natively:

    {"type": "custom", "engine": "dqx",
     "implementation": {"check": {"function": <fn>, "arguments": {...}},
                        "name": <name>, "criticality": "error" | "warn"}}

DQX's ``_is_dqx_explicit_rule`` only runs a rule when it is ``type=custom`` +
``engine=dqx`` + an ``implementation`` dict containing a ``check`` — so this module
is what makes a UI- or generator-authored rule *actually execute*.

Two design rules (see ``docs/dais/dqx-quality-rules-unification.md``):

  1. **Constraint-equivalent checks are NOT offered here.** Anything DQX derives
     automatically from ODCS property constraints (not-null/unique/pattern/range/
     length/format — see ``CONSTRAINT_DERIVED_FUNCTIONS``) is authored on the
     property's constraints, not as an explicit quality rule. ``CHECK_CATALOG``
     contains only checks that go *beyond* a constraint.
  2. **The authored thing is the executed thing.** The display string is derived
     from the check; there is no separate free-text ``rule`` field to drift.

Consumed by: the quality-rule authoring UI (via an API route), the agentic
contract generator, and the persistence layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── criticality ────────────────────────────────────────────────────────────────
# ODCS/Ontos `severity` → DQX `criticality`. Mirrors the aviation seed's mapping
# (`_DQX_CRITICALITY`) so generated/authored rules match hand-authored ones.
SEVERITY_TO_CRITICALITY: Dict[str, str] = {"error": "error", "warning": "warn"}


def to_criticality(severity: Optional[str]) -> str:
    """Map an Ontos severity to a DQX criticality (defaults to ``error``)."""
    return SEVERITY_TO_CRITICALITY.get((severity or "error").strip().lower(), "error")


# ── catalog metadata (drives the instructive authoring UI) ───────────────────────
@dataclass(frozen=True)
class CheckArg:
    """One argument of a DQX check, with the metadata the UI needs to teach it."""
    name: str
    # one of: string | number | integer | boolean | string[] | column | columns | sql
    type: str
    required: bool = True
    help: str = ""
    example: Any = None
    default: Any = None


@dataclass(frozen=True)
class CheckDef:
    """A DQX built-in check offered in the explicit-quality picker."""
    function: str
    label: str               # plain-language label, e.g. "In allowed list"
    description: str          # one-line explainer for the picker
    grain: str                # "column" | "object"
    args: tuple[CheckArg, ...]
    example: str = ""         # a concrete worked example for the UI
    in_v1_subset: bool = False
    # name of the arg auto-filled with the property name when authored on a column
    column_arg: Optional[str] = None


# Functions DQX derives from ODCS property constraints — authored on the property's
# Constraints, NOT offered as explicit quality rules. Listed so the UI/migration can
# recognise and redirect them.
CONSTRAINT_DERIVED_FUNCTIONS: frozenset = frozenset({
    "is_not_null", "is_not_null_and_not_empty", "is_not_empty",
    "regex_match",          # == `pattern`
    "is_in_range", "is_not_less_than", "is_not_greater_than",  # == minimum/maximum
    "is_valid_date", "is_valid_timestamp",                     # == date/timestamp format
})
# NOTE: `is_unique` is deliberately NOT here — it's only constraint-equivalent for a
# SINGLE column (== the `unique` constraint). Composite/multi-column uniqueness is a
# legitimate explicit check (it's in CHECK_CATALOG). The "this should be a constraint"
# nudge for single-column is_unique is an author-time arity check, not a blanket exclusion.


# The explicit-quality catalog: checks that go BEYOND a constraint. Arg schemas
# match DQX 0.15 `check_funcs.py` signatures exactly.
CHECK_CATALOG: tuple = (
    CheckDef(
        function="is_in_list",
        label="In allowed list",
        description="Value must be one of a fixed set of allowed values.",
        grain="column",
        column_arg="column",
        in_v1_subset=True,
        example="position_source ∈ {ADSB, MLAT, Mode-S}",
        args=(
            CheckArg("column", "column", help="Column to check."),
            CheckArg("allowed", "string[]", help="The allowed values.",
                     example=["ADSB", "MLAT", "Mode-S"]),
            CheckArg("case_sensitive", "boolean", required=False, default=True,
                     help="Case-sensitive comparison."),
        ),
    ),
    CheckDef(
        function="is_not_in_list",
        label="Not in forbidden list",
        description="Value must NOT be one of a set of forbidden values.",
        grain="column",
        column_arg="column",
        example="status ∉ {DELETED, PURGED}",
        args=(
            CheckArg("column", "column", help="Column to check."),
            CheckArg("forbidden", "string[]", help="The forbidden values."),
            CheckArg("case_sensitive", "boolean", required=False, default=True,
                     help="Case-sensitive comparison."),
        ),
    ),
    CheckDef(
        function="is_data_fresh",
        label="Fresh within N minutes",
        description="Timestamp column must be no older than N minutes (catches stale data).",
        grain="column",
        column_arg="column",
        in_v1_subset=True,
        example="ts_utc fresh within 60 minutes",
        args=(
            CheckArg("column", "column", help="Timestamp column to check."),
            CheckArg("max_age_minutes", "integer", help="Max age before data is stale.",
                     example=60),
            CheckArg("base_timestamp", "column", required=False,
                     help="Reference timestamp (defaults to current_timestamp())."),
        ),
    ),
    CheckDef(
        function="is_aggr_not_greater_than",
        label="Aggregate not above limit",
        description="An aggregate (count/sum/avg/…) over the table must not exceed a limit.",
        grain="object",
        in_v1_subset=True,
        example="count(*) not greater than 1_000_000",
        args=(
            CheckArg("column", "column", help="Column to aggregate (use '*' with count)."),
            CheckArg("limit", "number", help="The maximum allowed value.", example=1000000),
            CheckArg("aggr_type", "string", required=False, default="count",
                     help="count | sum | avg | min | max | stddev | …"),
            CheckArg("group_by", "string[]", required=False, help="Optional group-by columns."),
            CheckArg("row_filter", "sql", required=False, help="Optional SQL row filter."),
            CheckArg("aggr_params", "string", required=False,
                     help="Extra params for the aggregate (e.g. percentile value)."),
        ),
    ),
    CheckDef(
        function="is_unique",
        label="Unique (composite key)",
        description="A combination of columns must be unique across the table. "
                    "(Single-column uniqueness is a constraint, not this.)",
        grain="object",
        example="(flight_key, service_date) is unique",
        args=(
            CheckArg("columns", "columns", help="Columns whose combination must be unique.",
                     example=["flight_key", "service_date"]),
            CheckArg("nulls_distinct", "boolean", required=False, default=True,
                     help="Treat NULLs as distinct (SQL ANSI)."),
            CheckArg("row_filter", "sql", required=False,
                     help="Optional SQL filter to scope the uniqueness check (e.g. per partition)."),
        ),
    ),
    CheckDef(
        function="foreign_key",
        label="Foreign key exists",
        description="Values must exist in a reference table's column(s).",
        grain="object",
        in_v1_subset=True,
        example="dep_iata ∈ airports.iata_code",
        args=(
            # Order matches the user-facing DQX params (columns, ref_columns, ref_table);
            # DQX's internal `ref_df_name` is omitted. Reads naturally in the UI: this
            # table's column(s) → matching column(s) → which table.
            CheckArg("columns", "columns", help="Foreign-key column(s) in this table."),
            CheckArg("ref_columns", "columns", help="Matching column(s) in the reference table."),
            CheckArg("ref_table", "string", help="Reference table (catalog.schema.table)."),
            CheckArg("row_filter", "sql", required=False, help="Optional SQL row filter."),
        ),
    ),
    CheckDef(
        function="sql_expression",
        label="Custom SQL expression",
        description="Escape hatch — a SQL predicate that must hold for every row. "
                    "The SQL you write is exactly what DQX runs.",
        grain="column",   # also valid at object grain (cross-column predicates)
        in_v1_subset=True,
        example="scheduled_arr_utc > scheduled_dep_utc",
        args=(
            CheckArg("expression", "sql", help="A boolean SQL expression (pass = True)."),
            CheckArg("msg", "string", required=False, help="Message shown on failure."),
            CheckArg("negate", "boolean", required=False, default=False,
                     help="Invert: fail when the expression is TRUE."),
        ),
    ),
)


def catalog(grain: Optional[str] = None, v1_only: bool = False) -> List[CheckDef]:
    """The catalog, optionally filtered by grain ('column'/'object') and v1 subset."""
    out = list(CHECK_CATALOG)
    if grain is not None:
        out = [c for c in out if c.grain == grain or c.function == "sql_expression"]
    if v1_only:
        out = [c for c in out if c.in_v1_subset]
    return out


# ── the envelope (the only "compiler") ───────────────────────────────────────────
def build_implementation(
    function: str, arguments: Dict[str, Any], *, name: str, criticality: str
) -> Dict[str, Any]:
    """Wrap a DQX check ``{function, arguments}`` into the ODCS explicit-rule
    ``implementation`` dict that ``DataContractRulesGenerator`` executes."""
    return {
        "check": {"function": function, "arguments": dict(arguments)},
        "name": name,
        "criticality": criticality,
    }


def sql_expression_implementation(
    expression: str, msg: Optional[str], *, name: str, criticality: str
) -> Dict[str, Any]:
    """Convenience for the ``sql_expression`` escape hatch. Produces the exact shape
    the aviation seed's ``_qrule`` emits (the Phase-1 correctness anchor). ``msg`` is
    omitted from the arguments when None so the stored ODCS matches what a human would
    hand-author (no ``msg: null`` noise); DQX auto-generates a message in that case."""
    args: Dict[str, Any] = {"expression": expression}
    if msg is not None:
        args["msg"] = msg
    return build_implementation("sql_expression", args, name=name, criticality=criticality)


# ── display (derived from the check — never a separate authored field) ───────────
def to_display(check: Dict[str, Any], *, column: Optional[str] = None) -> str:
    """Readable one-liner derived from a DQX check dict, for list rendering."""
    fn = (check or {}).get("function", "")
    args = (check or {}).get("arguments") or {}
    col = args.get("column") or column or ""
    if fn == "sql_expression":
        return str(args.get("expression", "")).strip() or "(custom SQL)"
    if fn == "is_in_list":
        return f"{col} in {args.get('allowed', [])}"
    if fn == "is_not_in_list":
        return f"{col} not in {args.get('forbidden', [])}"
    if fn == "is_data_fresh":
        return f"{col} fresh within {args.get('max_age_minutes', '?')} min"
    if fn == "is_aggr_not_greater_than":
        return f"{args.get('aggr_type', 'count')}({col or '*'}) ≤ {args.get('limit', '?')}"
    if fn == "is_unique":
        return f"unique({', '.join(args.get('columns', []))})"
    if fn == "foreign_key":
        return f"{', '.join(args.get('columns', []))} → {args.get('ref_table', '?')}"
    # generic fallback: function + its column/args
    label = next((c.label for c in CHECK_CATALOG if c.function == fn), fn)
    return f"{label}{(' on ' + col) if col else ''}"


# ── serialization (for the authoring UI's check picker, via the API) ─────────────
def _serialize_arg(a: CheckArg) -> Dict[str, Any]:
    d: Dict[str, Any] = {"name": a.name, "type": a.type, "required": a.required}
    if a.help:
        d["help"] = a.help
    if a.example is not None:
        d["example"] = a.example
    if a.default is not None:
        d["default"] = a.default
    return d


def _serialize_check(c: CheckDef) -> Dict[str, Any]:
    return {
        "function": c.function,
        "label": c.label,
        "description": c.description,
        "grain": c.grain,
        "in_v1_subset": c.in_v1_subset,
        "example": c.example,
        "column_arg": c.column_arg,
        "args": [_serialize_arg(a) for a in c.args],
    }


def serialize_catalog() -> Dict[str, Any]:
    """JSON-serializable catalog for the authoring UI's check picker.

    ``checks`` are the explicit (non-constraint) DQX checks the picker offers;
    ``constraint_derived_functions`` lets the UI recognise + redirect anything that
    belongs on the property's Constraints tab instead."""
    return {
        "checks": [_serialize_check(c) for c in CHECK_CATALOG],
        "constraint_derived_functions": sorted(CONSTRAINT_DERIVED_FUNCTIONS),
    }
