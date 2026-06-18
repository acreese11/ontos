"""Transient `jobs.submit()` runs have no server-side job-parameter substitution.

The Run-DQX button submits a one-off run via `JobsManager.submit_workflow`, which must
resolve `{{job.parameters.NAME}}` placeholders itself. When the DQX validation task moved
from `spark_python_task` (parameters list) to `notebook_task` (base_parameters dict), the
resolver had to cover the dict shape too — otherwise the notebook's widgets receive literal
`{{job.parameters.contract_id}}` strings and every run fails. These tests pin the resolver.
"""
import os
os.environ['TESTING'] = 'true'
os.environ['SKIP_STARTUP_TASKS'] = 'true'

from src.controller.jobs_manager import _resolve_job_param_placeholder


PARAMS = {"contract_id": "abc-123", "schema_index": "0", "write_quarantine": "true"}


class TestResolveJobParamPlaceholder:
    def test_resolves_known_placeholder(self):
        assert _resolve_job_param_placeholder("{{job.parameters.contract_id}}", PARAMS) == "abc-123"

    def test_unknown_placeholder_resolves_to_empty(self):
        # Mirrors the old spark_python_task behavior: missing param → '' (not the literal).
        assert _resolve_job_param_placeholder("{{job.parameters.nope}}", PARAMS) == ""

    def test_non_placeholder_passthrough(self):
        assert _resolve_job_param_placeholder("literal-value", PARAMS) == "literal-value"
        assert _resolve_job_param_placeholder("0", PARAMS) == "0"

    def test_non_string_passthrough(self):
        assert _resolve_job_param_placeholder(0, PARAMS) == 0
        assert _resolve_job_param_placeholder(None, PARAMS) is None

    def test_partial_or_malformed_placeholders_passthrough(self):
        # Only fully-wrapped {{job.parameters.NAME}} tokens resolve; anything else is literal.
        assert _resolve_job_param_placeholder("{{job.parameters.contract_id", PARAMS) == "{{job.parameters.contract_id"
        assert _resolve_job_param_placeholder("prefix {{job.parameters.contract_id}}", PARAMS) == "prefix {{job.parameters.contract_id}}"

    def test_notebook_base_parameters_dict_resolution(self):
        # The exact shape submit_workflow applies for a notebook_task.
        base = {
            "contract_id": "{{job.parameters.contract_id}}",
            "schema_index": "{{job.parameters.schema_index}}",
            "pipeline_id": "dqx_contract_validation",  # literal, no placeholder
        }
        resolved = {k: _resolve_job_param_placeholder(v, PARAMS) for k, v in base.items()}
        assert resolved == {
            "contract_id": "abc-123",
            "schema_index": "0",
            "pipeline_id": "dqx_contract_validation",
        }
