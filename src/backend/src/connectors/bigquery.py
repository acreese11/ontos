"""
Google BigQuery Connector

This module implements the AssetConnector interface for Google BigQuery,
providing asset discovery, metadata retrieval, schema inspection, sample
data, and validation for BigQuery objects including tables, views,
materialized views, external tables, routines, and ML models.

Authentication priority:
  1. UC Connection (extract service account key from Databricks connection)
  2. Inline credentials JSON
  3. Service account key file path
  4. Application Default Credentials (ADC)
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.api_core.exceptions import (
    Forbidden,
    GoogleAPICallError,
    NotFound,
)
from google.cloud import bigquery
from google.oauth2 import service_account

from src.connectors.base import (
    AssetConnector,
    ConnectorCapabilities,
    ConnectorConfig,
    ConnectorAuthenticationError,
    ConnectorConnectionError,
    ConnectorPermissionError,
    ListAssetsOptions,
)
from src.models.assets import (
    AssetInfo,
    AssetMetadata,
    AssetOwnership,
    AssetStatistics,
    AssetValidationResult,
    ColumnInfo,
    SampleData,
    SchemaInfo,
    UnifiedAssetType,
)
from src.common.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# BigQuery Connector Configuration
# ============================================================================

class BigQueryConnectorConfig(ConnectorConfig):
    """Configuration specific to the BigQuery connector."""

    project_id: Optional[str] = None
    default_dataset: Optional[str] = None
    uc_connection_name: Optional[str] = None
    location: Optional[str] = None

    # UC Secrets reference for the GCP service account key JSON.
    # The secret value must contain the full JSON string of a GCP SA key.
    credentials_secret_scope: Optional[str] = None
    credentials_secret_key: Optional[str] = None

    # Fallback: local file path (dev only)
    credentials_path: Optional[str] = None

    # Workspace client injected at startup for UC Connection / Secrets access
    workspace_client: Optional[Any] = None

    model_config = {"from_attributes": True, "arbitrary_types_allowed": True}


# ============================================================================
# Table Type Mapping
# ============================================================================

_BQ_TABLE_TYPE_MAP: Dict[str, UnifiedAssetType] = {
    "TABLE": UnifiedAssetType.BQ_TABLE,
    "VIEW": UnifiedAssetType.BQ_VIEW,
    "MATERIALIZED_VIEW": UnifiedAssetType.BQ_MATERIALIZED_VIEW,
    "EXTERNAL": UnifiedAssetType.BQ_EXTERNAL_TABLE,
    "MODEL": UnifiedAssetType.BQ_MODEL,
    "SNAPSHOT": UnifiedAssetType.BQ_TABLE,
}


def _bq_type(table_type: Optional[str]) -> UnifiedAssetType:
    return _BQ_TABLE_TYPE_MAP.get(table_type or "", UnifiedAssetType.BQ_TABLE)


# ============================================================================
# BigQuery Connector
# ============================================================================

class BigQueryConnector(AssetConnector):
    """
    Asset connector for Google BigQuery.

    Supports:
    - Tables (managed, snapshot)
    - Views
    - Materialized Views
    - External Tables
    - Routines (UDFs / procedures)
    - BQML Models
    """

    connector_type = "bigquery"
    display_name = "Google BigQuery"
    description = "Connector for Google BigQuery datasets and tables"

    def __init__(
        self,
        config: Optional[BigQueryConnectorConfig] = None,
        workspace_client: Optional[Any] = None,
    ):
        super().__init__(config or BigQueryConnectorConfig())
        self._bq_client: Optional[bigquery.Client] = None
        self._ws_client = workspace_client
        if isinstance(self._config, BigQueryConnectorConfig) and self._config.workspace_client:
            self._ws_client = self._config.workspace_client

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    def _init_client(self) -> bigquery.Client:
        """Create and cache a BigQuery client with the configured credentials.

        Credential resolution order:
        1. UC Secrets (scope + key) — recommended for production
        2. UC Connection — provides projectId (credentials are redacted by Databricks)
        3. Local key file — dev/testing fallback
        4. Application Default Credentials
        """
        if self._bq_client is not None:
            return self._bq_client

        cfg: BigQueryConnectorConfig = self._config  # type: ignore[assignment]
        credentials = None
        project = cfg.project_id

        # 1. UC Connection (provides projectId; credentials are redacted)
        if cfg.uc_connection_name and self._ws_client:
            _, project_from_conn = self._credentials_from_uc_connection(
                cfg.uc_connection_name, project
            )
            project = project or project_from_conn

        # 2. UC Secrets — primary credential source
        if credentials is None and cfg.credentials_secret_scope and cfg.credentials_secret_key:
            credentials, project = self._credentials_from_uc_secret(
                cfg.credentials_secret_scope, cfg.credentials_secret_key, project
            )

        # 3. Key file (dev fallback)
        if credentials is None and cfg.credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                cfg.credentials_path
            )
            with open(cfg.credentials_path) as f:
                project = project or json.load(f).get("project_id")

        # 4. ADC (credentials=None lets the client discover them)

        try:
            self._bq_client = bigquery.Client(
                project=project,
                credentials=credentials,
                location=cfg.location,
            )
        except Exception as exc:
            raise ConnectorAuthenticationError(
                f"Failed to create BigQuery client: {exc}",
                connector_type=self.connector_type,
            ) from exc

        logger.info(
            f"BigQuery client initialised (project={self._bq_client.project}, "
            f"location={cfg.location or 'default'})"
        )
        return self._bq_client

    def _credentials_from_uc_connection(
        self, connection_name: str, fallback_project: Optional[str]
    ) -> tuple:
        """Extract GCP credentials and/or project ID from a Databricks UC Connection.

        Databricks redacts sensitive credential fields on read, so the service
        account key JSON is typically *not* available via ``connections.get()``.
        We still attempt to read it (in case future API changes expose it), but
        the main value is extracting the ``projectId`` that *is* returned.
        """
        try:
            conn = self._ws_client.connections.get(name=connection_name)
            options = conn.options or {}

            # Try to extract project ID (this IS returned by the API)
            uc_project = options.get("projectId") or options.get("project_id")
            project = fallback_project or uc_project

            # Attempt to read the SA key (usually redacted)
            sa_key = (
                options.get("GoogleServiceAccountKeyJson")
                or options.get("credentials")
                or options.get("google_service_account_key_json")
            )
            if sa_key:
                info = json.loads(sa_key)
                credentials = service_account.Credentials.from_service_account_info(info)
                project = project or info.get("project_id")
                logger.info(f"Loaded BQ credentials from UC Connection '{connection_name}'")
                return credentials, project

            if uc_project:
                logger.info(
                    f"UC Connection '{connection_name}' provided projectId='{uc_project}' "
                    f"(credentials are redacted by Databricks — using other auth method)"
                )
            else:
                logger.info(
                    f"UC Connection '{connection_name}' accessible but credentials are "
                    f"redacted by Databricks (keys present: {list(options.keys())})"
                )
            return None, project
        except Exception as exc:
            logger.warning(
                f"Could not read UC Connection '{connection_name}': {exc}"
            )
            return None, fallback_project

    def _credentials_from_uc_secret(
        self, scope: str, key: str, fallback_project: Optional[str]
    ) -> tuple:
        """Read GCP service account key JSON from a Databricks UC Secret."""
        import base64

        try:
            resp = self._ws_client.secrets.get_secret(scope=scope, key=key)
            raw = resp.value
            logger.debug(
                f"UC Secret '{scope}/{key}' response: type={type(raw).__name__}, "
                f"len={len(raw) if raw else 0}, "
                f"preview={repr(raw[:80]) if raw else 'None'}"
            )

            if not raw:
                logger.warning(f"UC Secret '{scope}/{key}' returned empty value")
                return None, fallback_project

            # The SDK may return bytes or str; normalise to str
            if isinstance(raw, bytes):
                text = raw.decode("utf-8")
            else:
                text = str(raw)

            # The REST API returns base64-encoded values; try to decode if
            # the value doesn't look like JSON already
            text = text.strip()
            if not text.startswith("{"):
                try:
                    text = base64.b64decode(text).decode("utf-8").strip()
                except Exception:
                    pass

            if not text or not text.startswith("{"):
                logger.warning(
                    f"UC Secret '{scope}/{key}' value is not valid JSON "
                    f"(starts with: {repr(text[:40])})"
                )
                return None, fallback_project

            info = json.loads(text)
            credentials = service_account.Credentials.from_service_account_info(info)
            project = fallback_project or info.get("project_id")
            logger.info(f"Loaded BQ credentials from UC Secret '{scope}/{key}'")
            return credentials, project
        except Exception as exc:
            logger.warning(f"Could not read UC Secret '{scope}/{key}': {exc}")
            return None, fallback_project

    def _ensure_client(self) -> bigquery.Client:
        return self._init_client()

    def set_workspace_client(self, client: Any) -> None:
        self._ws_client = client

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        if not self._config.enabled:
            return False
        try:
            self._ensure_client()
            return True
        except Exception:
            return False

    def _get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            can_list_assets=True,
            can_get_metadata=True,
            can_validate_exists=True,
            can_get_schema=True,
            can_get_sample_data=True,
            can_get_statistics=True,
            can_get_lineage=False,
            can_get_permissions=False,
            can_create_assets=False,
            can_update_assets=False,
            can_delete_assets=False,
            supported_asset_types=[
                UnifiedAssetType.BQ_TABLE,
                UnifiedAssetType.BQ_VIEW,
                UnifiedAssetType.BQ_MATERIALIZED_VIEW,
                UnifiedAssetType.BQ_EXTERNAL_TABLE,
                UnifiedAssetType.BQ_ROUTINE,
                UnifiedAssetType.BQ_MODEL,
            ],
        )

    # ------------------------------------------------------------------
    # list_assets
    # ------------------------------------------------------------------

    def list_assets(
        self,
        options: Optional[ListAssetsOptions] = None,
    ) -> List[AssetInfo]:
        """
        List BigQuery assets.

        Path semantics (dot-separated):
          - ""                     -> list datasets in the configured project
          - "project"              -> list datasets in that project
          - "project.dataset"      -> list tables / views / routines / models
          - "project.dataset.table" -> empty (table is a leaf; columns come
                                       from get_asset_metadata().schema_info)
        """
        client = self._ensure_client()
        options = options or ListAssetsOptions()
        results: List[AssetInfo] = []
        limit = options.limit

        try:
            path = options.path or ""
            parts = path.split(".") if path else []

            if len(parts) <= 1:
                project = parts[0] if parts and parts[0] else client.project
                results.extend(self._list_datasets(client, project, options, limit))
            elif len(parts) == 2:
                project = parts[0]
                dataset = parts[1]
                asset_types = options.asset_types

                table_types = {
                    UnifiedAssetType.BQ_TABLE,
                    UnifiedAssetType.BQ_VIEW,
                    UnifiedAssetType.BQ_MATERIALIZED_VIEW,
                    UnifiedAssetType.BQ_EXTERNAL_TABLE,
                }
                if not asset_types or table_types & set(asset_types):
                    results.extend(
                        self._list_tables(client, project, dataset, options, limit - len(results))
                    )

                if not asset_types or UnifiedAssetType.BQ_ROUTINE in asset_types:
                    if len(results) < limit:
                        results.extend(
                            self._list_routines(
                                client, project, dataset, options, limit - len(results)
                            )
                        )

                if not asset_types or UnifiedAssetType.BQ_MODEL in asset_types:
                    if len(results) < limit:
                        results.extend(
                            self._list_models(
                                client, project, dataset, options, limit - len(results)
                            )
                        )
            # len(parts) >= 3 means a specific table/view/routine — leaf node,
            # no children to list (columns are in schema_info, not listed here)

            return results[:limit]

        except Forbidden as exc:
            logger.warning(f"Permission denied listing BQ assets: {exc}")
            raise ConnectorPermissionError(str(exc), self.connector_type) from exc
        except GoogleAPICallError as exc:
            logger.error(f"BigQuery API error listing assets: {exc}")
            raise ConnectorConnectionError(str(exc), self.connector_type) from exc

    # -- list helpers ------------------------------------------------------

    def _list_datasets(
        self,
        client: bigquery.Client,
        project: str,
        options: ListAssetsOptions,
        limit: int,
    ) -> List[AssetInfo]:
        results: List[AssetInfo] = []
        search = (options.search_term or "").lower()
        for ds in client.list_datasets(project=project, max_results=limit * 2):
            if len(results) >= limit:
                break
            name = ds.dataset_id
            if search and search not in name.lower():
                continue
            results.append(
                AssetInfo(
                    identifier=f"{ds.project}.{name}",
                    name=name,
                    asset_type=UnifiedAssetType.BQ_DATASET,
                    connector_type=self.connector_type,
                    path=f"{ds.project}.{name}",
                    catalog=ds.project,
                )
            )
        return results

    def _list_tables(
        self,
        client: bigquery.Client,
        project: str,
        dataset: str,
        options: ListAssetsOptions,
        limit: int,
    ) -> List[AssetInfo]:
        results: List[AssetInfo] = []
        search = (options.search_term or "").lower()
        dataset_ref = bigquery.DatasetReference(project, dataset)
        try:
            for tbl in client.list_tables(dataset_ref, max_results=limit * 2):
                if len(results) >= limit:
                    break
                if search and search not in tbl.table_id.lower():
                    continue
                asset_type = _bq_type(tbl.table_type)
                if options.asset_types and asset_type not in options.asset_types:
                    continue
                fqn = f"{project}.{dataset}.{tbl.table_id}"
                results.append(
                    AssetInfo(
                        identifier=fqn,
                        name=tbl.table_id,
                        asset_type=asset_type,
                        connector_type=self.connector_type,
                        path=fqn,
                        catalog=project,
                        schema_name=dataset,
                    )
                )
        except (NotFound, Forbidden) as exc:
            logger.debug(f"Cannot list tables in {project}.{dataset}: {exc}")
        return results

    def _list_routines(
        self,
        client: bigquery.Client,
        project: str,
        dataset: str,
        options: ListAssetsOptions,
        limit: int,
    ) -> List[AssetInfo]:
        results: List[AssetInfo] = []
        search = (options.search_term or "").lower()
        try:
            for routine in client.list_routines(f"{project}.{dataset}", max_results=limit * 2):
                if len(results) >= limit:
                    break
                name = routine.routine_id
                if search and search not in name.lower():
                    continue
                fqn = f"{project}.{dataset}.{name}"
                results.append(
                    AssetInfo(
                        identifier=fqn,
                        name=name,
                        asset_type=UnifiedAssetType.BQ_ROUTINE,
                        connector_type=self.connector_type,
                        path=fqn,
                        catalog=project,
                        schema_name=dataset,
                    )
                )
        except (NotFound, Forbidden) as exc:
            logger.debug(f"Cannot list routines in {project}.{dataset}: {exc}")
        except Exception as exc:
            logger.debug(f"Error listing routines in {project}.{dataset}: {exc}")
        return results

    def _list_models(
        self,
        client: bigquery.Client,
        project: str,
        dataset: str,
        options: ListAssetsOptions,
        limit: int,
    ) -> List[AssetInfo]:
        results: List[AssetInfo] = []
        search = (options.search_term or "").lower()
        try:
            for model in client.list_models(f"{project}.{dataset}", max_results=limit * 2):
                if len(results) >= limit:
                    break
                name = model.model_id
                if search and search not in name.lower():
                    continue
                fqn = f"{project}.{dataset}.{name}"
                results.append(
                    AssetInfo(
                        identifier=fqn,
                        name=name,
                        asset_type=UnifiedAssetType.BQ_MODEL,
                        connector_type=self.connector_type,
                        path=fqn,
                        catalog=project,
                        schema_name=dataset,
                    )
                )
        except (NotFound, Forbidden) as exc:
            logger.debug(f"Cannot list models in {project}.{dataset}: {exc}")
        except Exception as exc:
            logger.debug(f"Error listing models in {project}.{dataset}: {exc}")
        return results

    # ------------------------------------------------------------------
    # get_asset_metadata
    # ------------------------------------------------------------------

    def get_asset_metadata(self, identifier: str) -> Optional[AssetMetadata]:
        client = self._ensure_client()
        parts = identifier.split(".") if identifier else []

        if not parts:
            return None

        try:
            # Single part -> project (mapped to Catalog)
            if len(parts) == 1:
                return self._get_project_metadata(client, parts[0])

            # Two parts -> dataset (mapped to Schema)
            if len(parts) == 2:
                return self._get_dataset_metadata(client, parts[0], parts[1])

            # Three+ parts -> leaf asset
            metadata = self._get_table_metadata(client, identifier)
            if metadata:
                return metadata

            metadata = self._get_routine_metadata(client, identifier)
            if metadata:
                return metadata

            metadata = self._get_model_metadata(client, identifier)
            if metadata:
                return metadata

            logger.debug(f"BQ asset not found: {identifier}")
            return None

        except Forbidden as exc:
            logger.warning(f"Permission denied for {identifier}: {exc}")
            raise ConnectorPermissionError(str(exc), self.connector_type) from exc
        except GoogleAPICallError as exc:
            logger.error(f"BQ API error for {identifier}: {exc}")
            return None

    def _get_project_metadata(
        self, client: bigquery.Client, project: str,
    ) -> Optional[AssetMetadata]:
        """Return lightweight metadata for a BQ project (mapped to Catalog)."""
        return AssetMetadata(
            identifier=project,
            name=project,
            asset_type=UnifiedAssetType.BQ_PROJECT,
            connector_type=self.connector_type,
            description=None,
            path=project,
            catalog=project,
            exists=True,
        )

    def _get_dataset_metadata(
        self, client: bigquery.Client, project: str, dataset_id: str,
    ) -> Optional[AssetMetadata]:
        """Return metadata for a BQ dataset (mapped to Schema)."""
        try:
            ds = client.get_dataset(f"{project}.{dataset_id}")
            path = f"{project}.{dataset_id}"

            created_at = ds.created
            modified_at = ds.modified
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if modified_at and modified_at.tzinfo is None:
                modified_at = modified_at.replace(tzinfo=timezone.utc)

            return AssetMetadata(
                identifier=path,
                name=dataset_id,
                asset_type=UnifiedAssetType.BQ_DATASET,
                connector_type=self.connector_type,
                description=ds.description,
                path=path,
                catalog=project,
                schema_name=dataset_id,
                location=ds.location,
                tags=dict(ds.labels or {}),
                properties={"location": ds.location, "default_table_expiration_ms": ds.default_table_expiration_ms},
                created_at=created_at,
                updated_at=modified_at,
                exists=True,
            )
        except NotFound:
            return None
        except Exception as exc:
            logger.debug(f"Error getting dataset metadata for {project}.{dataset_id}: {exc}")
            return None

    def _get_table_metadata(
        self, client: bigquery.Client, identifier: str
    ) -> Optional[AssetMetadata]:
        try:
            table = client.get_table(identifier)
        except NotFound:
            return None
        except Exception as exc:
            logger.debug(f"Error getting table metadata for {identifier}: {exc}")
            return None

        asset_type = _bq_type(table.table_type)

        schema_info = None
        if table.schema:
            columns = [
                ColumnInfo(
                    name=field.name,
                    data_type=field.field_type,
                    logical_type=field.mode,
                    nullable=(field.mode != "REQUIRED"),
                    description=field.description,
                    is_partition_key=False,
                )
                for field in table.schema
            ]
            partition_cols = []
            if table.time_partitioning and table.time_partitioning.field:
                partition_cols.append(table.time_partitioning.field)
            if table.range_partitioning and table.range_partitioning.field:
                partition_cols.append(table.range_partitioning.field)
            for col in columns:
                if col.name in partition_cols:
                    col.is_partition_key = True
            schema_info = SchemaInfo(
                columns=columns,
                partition_columns=partition_cols or None,
            )

        statistics = AssetStatistics(
            row_count=table.num_rows,
            size_bytes=table.num_bytes,
            updated_at=table.modified,
        )

        properties: Dict[str, Any] = dict(table.labels or {})
        if table.clustering_fields:
            properties["clustering_fields"] = table.clustering_fields
        if table.time_partitioning:
            properties["time_partitioning_type"] = table.time_partitioning.type_
            properties["time_partitioning_field"] = table.time_partitioning.field
        if table.range_partitioning:
            properties["range_partitioning_field"] = table.range_partitioning.field
        if table.table_type:
            properties["table_type"] = table.table_type

        created_at = table.created
        modified_at = table.modified
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if modified_at and modified_at.tzinfo is None:
            modified_at = modified_at.replace(tzinfo=timezone.utc)

        return AssetMetadata(
            identifier=str(table.reference),
            name=table.table_id,
            asset_type=asset_type,
            connector_type=self.connector_type,
            description=table.description,
            comment=table.description,
            path=str(table.reference),
            location=table.location,
            catalog=table.project,
            schema_name=table.dataset_id,
            schema_info=schema_info,
            ownership=AssetOwnership(),
            statistics=statistics,
            tags=dict(table.labels or {}),
            properties=properties,
            created_at=created_at,
            updated_at=modified_at,
            exists=True,
        )

    def _get_routine_metadata(
        self, client: bigquery.Client, identifier: str
    ) -> Optional[AssetMetadata]:
        try:
            routine = client.get_routine(identifier)
        except NotFound:
            return None
        except Exception as exc:
            logger.debug(f"Error getting routine metadata for {identifier}: {exc}")
            return None

        schema_info = None
        if routine.arguments:
            columns = [
                ColumnInfo(
                    name=arg.name or f"arg_{i}",
                    data_type=arg.data_type.type_kind if arg.data_type else "UNKNOWN",
                    description=None,
                )
                for i, arg in enumerate(routine.arguments)
            ]
            schema_info = SchemaInfo(columns=columns)

        properties: Dict[str, Any] = {}
        if routine.return_type:
            properties["return_type"] = routine.return_type.type_kind
        if routine.type_:
            properties["routine_type"] = routine.type_
        if routine.language:
            properties["language"] = routine.language

        created_at = routine.created
        modified_at = routine.modified
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if modified_at and modified_at.tzinfo is None:
            modified_at = modified_at.replace(tzinfo=timezone.utc)

        ref = routine.reference
        return AssetMetadata(
            identifier=str(ref),
            name=ref.routine_id,
            asset_type=UnifiedAssetType.BQ_ROUTINE,
            connector_type=self.connector_type,
            description=routine.description,
            path=str(ref),
            catalog=ref.project,
            schema_name=ref.dataset_id,
            schema_info=schema_info,
            properties=properties,
            created_at=created_at,
            updated_at=modified_at,
            exists=True,
        )

    def _get_model_metadata(
        self, client: bigquery.Client, identifier: str
    ) -> Optional[AssetMetadata]:
        try:
            model = client.get_model(identifier)
        except NotFound:
            return None
        except Exception as exc:
            logger.debug(f"Error getting model metadata for {identifier}: {exc}")
            return None

        properties: Dict[str, Any] = dict(model.labels or {})
        if model.model_type:
            properties["model_type"] = model.model_type.name if hasattr(model.model_type, "name") else str(model.model_type)

        created_at = model.created
        modified_at = model.modified
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if modified_at and modified_at.tzinfo is None:
            modified_at = modified_at.replace(tzinfo=timezone.utc)

        ref = model.reference
        return AssetMetadata(
            identifier=str(ref),
            name=ref.model_id,
            asset_type=UnifiedAssetType.BQ_MODEL,
            connector_type=self.connector_type,
            description=model.description,
            path=str(ref),
            catalog=ref.project,
            schema_name=ref.dataset_id,
            tags=dict(model.labels or {}),
            properties=properties,
            created_at=created_at,
            updated_at=modified_at,
            exists=True,
        )

    # ------------------------------------------------------------------
    # validate_asset_exists
    # ------------------------------------------------------------------

    def validate_asset_exists(self, identifier: str) -> AssetValidationResult:
        client = self._ensure_client()
        try:
            table = client.get_table(identifier)
            return AssetValidationResult(
                identifier=identifier,
                exists=True,
                validated=True,
                asset_type=_bq_type(table.table_type),
                message="Asset found",
                details={
                    "name": table.table_id,
                    "project": table.project,
                    "dataset": table.dataset_id,
                    "table_type": table.table_type,
                },
            )
        except NotFound:
            pass
        except Exception as exc:
            logger.debug(f"Table check failed for {identifier}: {exc}")

        # Try as routine
        try:
            client.get_routine(identifier)
            return AssetValidationResult(
                identifier=identifier,
                exists=True,
                validated=True,
                asset_type=UnifiedAssetType.BQ_ROUTINE,
                message="Routine found",
            )
        except NotFound:
            pass
        except Exception:
            pass

        # Try as model
        try:
            client.get_model(identifier)
            return AssetValidationResult(
                identifier=identifier,
                exists=True,
                validated=True,
                asset_type=UnifiedAssetType.BQ_MODEL,
                message="Model found",
            )
        except NotFound:
            pass
        except Exception:
            pass

        return AssetValidationResult(
            identifier=identifier,
            exists=False,
            validated=True,
            message="Asset not found in BigQuery",
        )

    # ------------------------------------------------------------------
    # get_sample_data
    # ------------------------------------------------------------------

    def get_sample_data(
        self, identifier: str, limit: int = 100
    ) -> Optional[SampleData]:
        client = self._ensure_client()

        validation = self.validate_asset_exists(identifier)
        if not validation.exists:
            return None
        if validation.asset_type not in (
            UnifiedAssetType.BQ_TABLE,
            UnifiedAssetType.BQ_VIEW,
            UnifiedAssetType.BQ_MATERIALIZED_VIEW,
            UnifiedAssetType.BQ_EXTERNAL_TABLE,
        ):
            logger.debug(f"Asset {identifier} does not support sample data")
            return None

        try:
            query = f"SELECT * FROM `{identifier}` LIMIT {limit}"
            result = client.query(query).result()
            columns = [field.name for field in result.schema]
            rows = [[str(v) if v is not None else None for v in row.values()] for row in result]
            return SampleData(
                columns=columns,
                rows=rows,
                sample_size=len(rows),
                truncated=len(rows) >= limit,
            )
        except Exception as exc:
            logger.warning(f"Error getting sample data for {identifier}: {exc}")
            return None

    # ------------------------------------------------------------------
    # list_containers
    # ------------------------------------------------------------------

    def list_containers(
        self, parent_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        client = self._ensure_client()
        containers: List[Dict[str, Any]] = []

        try:
            if parent_path is None:
                for ds in client.list_datasets():
                    containers.append({
                        "name": ds.dataset_id,
                        "type": "dataset",
                        "path": f"{ds.project}.{ds.dataset_id}",
                        "comment": None,
                        "has_children": True,
                    })
            else:
                parts = parent_path.split(".")
                # 3+ parts = table-level path — no container children
                if len(parts) >= 3:
                    return containers
                project = parts[0] if parts else client.project
                dataset = parts[1] if len(parts) > 1 else parts[0]
                dataset_ref = bigquery.DatasetReference(project, dataset)
                for tbl in client.list_tables(dataset_ref):
                    containers.append({
                        "name": tbl.table_id,
                        "type": tbl.table_type or "TABLE",
                        "path": f"{project}.{dataset}.{tbl.table_id}",
                        "comment": None,
                        "has_children": False,
                    })
        except Exception as exc:
            logger.warning(f"Error listing containers for {parent_path}: {exc}")
            raise ConnectorConnectionError(f"Failed to list resources: {exc}", connector_type=self.connector_type) from exc

        return containers

    # ------------------------------------------------------------------
    # health_check
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "connector_type": self.connector_type,
            "available": False,
            "enabled": self._config.enabled,
        }
        try:
            client = self._ensure_client()
            datasets = list(client.list_datasets(max_results=1))
            result["available"] = True
            result["healthy"] = True
            result["project"] = client.project
            result["dataset_count_sample"] = len(datasets)
        except Exception as exc:
            result["healthy"] = False
            result["error"] = str(exc)
        return result

    # ------------------------------------------------------------------
    # Identifier helpers (BigQuery uses project.dataset.table)
    # ------------------------------------------------------------------

    def _parse_identifier(self, identifier: str) -> Dict[str, Optional[str]]:
        parts = identifier.split(".")
        return {
            "catalog": parts[0] if len(parts) >= 3 else None,
            "schema": parts[1] if len(parts) >= 3 else (parts[0] if len(parts) == 2 else None),
            "name": parts[2] if len(parts) >= 3 else (parts[1] if len(parts) == 2 else parts[0] if parts else None),
        }
