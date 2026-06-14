"""
Unit tests for the Databricks connector.

These tests exercise pure metadata-mapping logic that does not require a live
WorkspaceClient — the client is a Mock whose `tables.get` returns fake column
objects, so no network or credentials are involved.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.connectors.databricks import DatabricksConnector


def _make_column(name, type_text="STRING", type_name="STRING", partition_index=None):
    """Build a duck-typed SDK ColumnInfo-like object."""
    return SimpleNamespace(
        name=name,
        type_text=type_text,
        type_name=SimpleNamespace(value=type_name),
        nullable=True,
        comment=None,
        partition_index=partition_index,
    )


def _make_connector_with_columns(columns):
    """Construct a connector whose `tables.get` returns a table with `columns`."""
    ws = MagicMock()
    table = SimpleNamespace(
        full_name="cat.sch.tbl",
        name="tbl",
        table_type="MANAGED",
        columns=columns,
        comment=None,
        storage_location=None,
        catalog_name="cat",
        schema_name="sch",
        owner=None,
        properties={},
        table_constraints=None,
    )
    ws.tables.get.return_value = table
    return DatabricksConnector(workspace_client=ws), ws


class TestDatabricksConnectorSchema:
    """Schema-mapping behavior for `_get_table_metadata`."""

    def test_infer_drops_rescued_and_metadata_columns(self):
        """`_rescued_data` and `_metadata` system columns must be dropped from
        the inferred schema, while real columns are preserved."""
        columns = [
            _make_column("id"),
            _make_column("_rescued_data"),
            _make_column("name"),
            _make_column("_metadata"),
        ]
        connector, _ws = _make_connector_with_columns(columns)

        metadata = connector._get_table_metadata(_ws, "cat.sch.tbl")

        assert metadata is not None
        assert metadata.schema_info is not None
        names = [c.name for c in metadata.schema_info.columns]
        assert names == ["id", "name"]
        assert "_rescued_data" not in names
        assert "_metadata" not in names

    def test_infer_drops_system_columns_from_partition_list(self):
        """System columns must also be excluded from partition_columns."""
        columns = [
            _make_column("event_date", partition_index=0),
            _make_column("_metadata", partition_index=1),
            _make_column("payload"),
        ]
        connector, _ws = _make_connector_with_columns(columns)

        metadata = connector._get_table_metadata(_ws, "cat.sch.tbl")

        assert metadata is not None
        assert metadata.schema_info is not None
        assert metadata.schema_info.partition_columns == ["event_date"]
