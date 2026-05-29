"""Entity Iteration Framework for Compliance Checks.

This module provides a framework for loading and filtering entities
(catalogs, schemas, tables, data products, etc.) for compliance evaluation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Protocol
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from src.common.logging import get_logger
from src.common.compliance_dsl import Lexer, Parser, Evaluator

logger = get_logger(__name__)


@dataclass
class EntityFilter:
    """Filter criteria for entities."""
    entity_types: List[str]  # Types to include (e.g., ['table', 'view'])
    where_clause_ast: Optional[Any] = None  # Parsed WHERE condition AST


class EntityLoader(ABC):
    """Base class for entity loaders."""

    @abstractmethod
    def get_supported_types(self) -> List[str]:
        """Return list of entity types this loader supports."""
        pass

    @abstractmethod
    def load_entities(
        self,
        entity_types: List[str],
        batch_size: int = 100
    ) -> Iterator[Dict[str, Any]]:
        """Load entities of specified types.

        Args:
            entity_types: List of entity types to load
            batch_size: Number of entities per batch

        Yields:
            Entity dictionaries
        """
        pass


class UnityCatalogLoader(EntityLoader):
    """Load entities from Unity Catalog."""

    def __init__(self, workspace_client):
        self.ws = workspace_client

    def get_supported_types(self) -> List[str]:
        return ['catalog', 'schema', 'table', 'view', 'function', 'volume']

    def load_entities(
        self,
        entity_types: List[str],
        batch_size: int = 100
    ) -> Iterator[Dict[str, Any]]:
        """Load UC entities."""
        try:
            # Load catalogs
            if 'catalog' in entity_types:
                for catalog in self.ws.catalogs.list():
                    yield {
                        'type': 'catalog',
                        'name': catalog.name,
                        'id': catalog.name,
                        'full_name': catalog.name,
                        'owner': getattr(catalog, 'owner', None),
                        'comment': getattr(catalog, 'comment', None),
                        'created_at': getattr(catalog, 'created_at', None),
                        'updated_at': getattr(catalog, 'updated_at', None),
                    }

            # Load schemas
            if 'schema' in entity_types:
                for catalog in self.ws.catalogs.list():
                    try:
                        for schema in self.ws.schemas.list(catalog_name=catalog.name):
                            yield {
                                'type': 'schema',
                                'name': schema.name,
                                'id': f"{catalog.name}.{schema.name}",
                                'full_name': schema.full_name or f"{catalog.name}.{schema.name}",
                                'catalog': catalog.name,
                                'owner': getattr(schema, 'owner', None),
                                'comment': getattr(schema, 'comment', None),
                                'created_at': getattr(schema, 'created_at', None),
                                'updated_at': getattr(schema, 'updated_at', None),
                            }
                    except Exception:
                        logger.exception(f"Failed to list schemas for catalog {catalog.name}")

            # Load tables and views
            if 'table' in entity_types or 'view' in entity_types:
                for catalog in self.ws.catalogs.list():
                    try:
                        for schema in self.ws.schemas.list(catalog_name=catalog.name):
                            try:
                                for table in self.ws.tables.list(
                                    catalog_name=catalog.name,
                                    schema_name=schema.name
                                ):
                                    table_type_raw = getattr(table, 'table_type', 'TABLE')
                                    entity_type = 'view' if table_type_raw == 'VIEW' else 'table'

                                    if entity_type not in entity_types:
                                        continue

                                    yield {
                                        'type': entity_type,
                                        'name': table.name,
                                        'id': getattr(table, 'full_name', f"{catalog.name}.{schema.name}.{table.name}"),
                                        'full_name': getattr(table, 'full_name', f"{catalog.name}.{schema.name}.{table.name}"),
                                        'catalog': catalog.name,
                                        'schema': schema.name,
                                        'table_type': table_type_raw,
                                        'owner': getattr(table, 'owner', None),
                                        'comment': getattr(table, 'comment', None),
                                        'created_at': getattr(table, 'created_at', None),
                                        'updated_at': getattr(table, 'updated_at', None),
                                        'storage_location': getattr(table, 'storage_location', None),
                                    }
                            except Exception:
                                logger.exception(f"Failed to list tables for schema {catalog.name}.{schema.name}")
                    except Exception:
                        logger.exception(f"Failed to list schemas for catalog {catalog.name}")

            # Load functions
            if 'function' in entity_types:
                for catalog in self.ws.catalogs.list():
                    try:
                        for schema in self.ws.schemas.list(catalog_name=catalog.name):
                            try:
                                for function in self.ws.functions.list(
                                    catalog_name=catalog.name,
                                    schema_name=schema.name
                                ):
                                    yield {
                                        'type': 'function',
                                        'name': function.name,
                                        'id': getattr(function, 'full_name', f"{catalog.name}.{schema.name}.{function.name}"),
                                        'full_name': getattr(function, 'full_name', f"{catalog.name}.{schema.name}.{function.name}"),
                                        'catalog': catalog.name,
                                        'schema': schema.name,
                                        'owner': getattr(function, 'owner', None),
                                        'comment': getattr(function, 'comment', None),
                                        'created_at': getattr(function, 'created_at', None),
                                        'updated_at': getattr(function, 'updated_at', None),
                                    }
                            except Exception:
                                logger.exception(f"Failed to list functions for schema {catalog.name}.{schema.name}")
                    except Exception:
                        logger.exception(f"Failed to list schemas for catalog {catalog.name}")

            # Load volumes
            if 'volume' in entity_types:
                for catalog in self.ws.catalogs.list():
                    try:
                        for schema in self.ws.schemas.list(catalog_name=catalog.name):
                            try:
                                for volume in self.ws.volumes.list(
                                    catalog_name=catalog.name,
                                    schema_name=schema.name
                                ):
                                    yield {
                                        'type': 'volume',
                                        'name': volume.name,
                                        'id': getattr(volume, 'full_name', f"{catalog.name}.{schema.name}.{volume.name}"),
                                        'full_name': getattr(volume, 'full_name', f"{catalog.name}.{schema.name}.{volume.name}"),
                                        'catalog': catalog.name,
                                        'schema': schema.name,
                                        'owner': getattr(volume, 'owner', None),
                                        'comment': getattr(volume, 'comment', None),
                                        'created_at': getattr(volume, 'created_at', None),
                                        'updated_at': getattr(volume, 'updated_at', None),
                                        'storage_location': getattr(volume, 'storage_location', None),
                                    }
                            except Exception:
                                logger.exception(f"Failed to list volumes for schema {catalog.name}.{schema.name}")
                    except Exception:
                        logger.exception(f"Failed to list schemas for catalog {catalog.name}")

        except Exception:
            logger.exception("Failed to load UC entities")


class AppEntityLoader(EntityLoader):
    """Load entities from application database."""

    def __init__(self, db: Session):
        self.db = db

    def get_supported_types(self) -> List[str]:
        return [
            'data_product',
            'data_contract',
            'domain',
            'glossary_term',
            'review',
        ]

    def load_entities(
        self,
        entity_types: List[str],
        batch_size: int = 100
    ) -> Iterator[Dict[str, Any]]:
        """Load app entities from database."""
        try:
            # Data Products
            if 'data_product' in entity_types:
                from src.repositories.data_products_repository import data_product_repo
                products = data_product_repo.list(self.db)
                for product in products:
                    yield {
                        'type': 'data_product',
                        'id': product.id,
                        'name': product.name,
                        'description': product.description,
                        'domain': product.domain,
                        'status': product.status,
                        'version': product.version,
                        'owner': product.owner,
                        'tags': product.tags or {},
                        'created_at': product.created_at,
                        'updated_at': product.updated_at,
                    }

            # Data Contracts
            if 'data_contract' in entity_types:
                from datetime import datetime, timedelta, timezone
                from src.db_models.quality import QualityItemDb
                from src.repositories.data_contracts_repository import data_contract_repo
                contracts = data_contract_repo.get_multi(self.db, skip=0, limit=10000)
                recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

                # Bulk-fetch the latest QualityItem per contract in one query
                # instead of a per-contract .first() (N+1). Subquery gets
                # max(measured_at) per entity_id; join back to pull the row.
                latest_at_subq = (
                    self.db.query(
                        QualityItemDb.entity_id.label('entity_id'),
                        func.max(QualityItemDb.measured_at).label('max_at'),
                    )
                    .filter(QualityItemDb.entity_type == 'data_contract')
                    .group_by(QualityItemDb.entity_id)
                    .subquery()
                )
                latest_rows = (
                    self.db.query(QualityItemDb)
                    .join(
                        latest_at_subq,
                        and_(
                            QualityItemDb.entity_id == latest_at_subq.c.entity_id,
                            QualityItemDb.measured_at == latest_at_subq.c.max_at,
                        ),
                    )
                    .filter(QualityItemDb.entity_type == 'data_contract')
                    .order_by(QualityItemDb.measured_at.desc(), QualityItemDb.id.desc())
                    .all()
                )
                # On a measured_at tie (e.g. two items inserted in the same
                # instant), keep the higher id (later insert) deterministically:
                # rows are newest-first, so setdefault keeps the first seen.
                latest_by_contract: Dict[str, QualityItemDb] = {}
                for r in latest_rows:
                    latest_by_contract.setdefault(r.entity_id, r)

                def _as_aware(dt):
                    # QualityItemDb.measured_at is TIMESTAMP(timezone=True), but
                    # whether the driver returns tz-aware or naive varies
                    # (psycopg2 vs psycopg3 / Lakebase). Comparing naive >= aware
                    # raises TypeError, which the caller's broad except swallows
                    # and silently zeroes the compliance score. Normalize to UTC.
                    if dt is not None and dt.tzinfo is None:
                        return dt.replace(tzinfo=timezone.utc)
                    return dt

                for contract in contracts:
                    # Derive enforcement signals from the federated QualityItem
                    # stream so compliance policies can answer "is this contract
                    # actually being enforced by some pipeline?"
                    latest_q = latest_by_contract.get(str(contract.id))
                    measured_at = _as_aware(latest_q.measured_at) if latest_q else None
                    has_recent = bool(measured_at and measured_at >= recent_cutoff)
                    yield {
                        'type': 'data_contract',
                        'id': contract.id,
                        'name': contract.name,
                        'description': contract.description_purpose,
                        'status': contract.status,
                        'version': contract.version,
                        'owner_team_id': contract.owner_team_id,
                        # DataContractDb.tags is a relationship to DataContractTagDb,
                        # not a JSON dict — wrap defensively.
                        'tags': [],
                        'created_at': contract.created_at,
                        'updated_at': contract.updated_at,
                        # Federated quality signals — derived from QualityItemDb
                        'has_recent_quality_metric': has_recent,
                        'latest_quality_score': float(latest_q.score_percent) if latest_q else None,
                        'latest_quality_source': latest_q.source if latest_q else None,
                        'latest_quality_at': latest_q.measured_at if latest_q else None,
                    }

            # Domains
            if 'domain' in entity_types:
                from src.repositories.domains_repository import domain_repo
                domains = domain_repo.list(self.db)
                for domain in domains:
                    yield {
                        'type': 'domain',
                        'id': domain.id,
                        'name': domain.name,
                        'description': domain.description,
                        'owner': domain.owner,
                        'tags': domain.tags or {},
                        'created_at': domain.created_at,
                        'updated_at': domain.updated_at,
                    }

            # Glossary Terms - Now stored as RDF concepts in KnowledgeCollections
            # Compliance checks for glossary terms should query the semantic models manager
            # TODO: Implement compliance entity fetching from RDF-based knowledge collections
            # if 'glossary_term' in entity_types:
            #     # Glossary terms are now managed via SemanticModelsManager as OntologyConcepts
            #     pass

            # Reviews
            if 'review' in entity_types:
                from src.repositories.data_asset_review_repository import data_asset_review_repo
                reviews = data_asset_review_repo.list(self.db)
                for review in reviews:
                    yield {
                        'type': 'review',
                        'id': review.id,
                        'asset_id': review.asset_id,
                        'asset_type': review.asset_type,
                        'status': review.status,
                        'reviewer': review.reviewer,
                        'requester': review.requester,
                        'created_at': review.created_at,
                        'updated_at': review.updated_at,
                    }

        except Exception:
            logger.exception("Failed to load app entities")


class EntityIterator:
    """Iterate over entities with filtering."""

    def __init__(self, loaders: List[EntityLoader]):
        self.loaders = loaders

    def iterate(
        self,
        entity_filter: EntityFilter,
        limit: Optional[int] = None,
        batch_size: int = 100
    ) -> Iterator[Dict[str, Any]]:
        """Iterate over filtered entities.

        Args:
            entity_filter: Filter criteria
            limit: Maximum number of entities to return
            batch_size: Batch size for loading

        Yields:
            Filtered entity dictionaries
        """
        count = 0

        for loader in self.loaders:
            # Check if loader supports any of the requested types
            supported = loader.get_supported_types()
            requested = [t for t in entity_filter.entity_types if t in supported]

            if not requested:
                continue

            # Load entities
            for entity in loader.load_entities(requested, batch_size):
                # Apply WHERE filter if present
                if entity_filter.where_clause_ast:
                    try:
                        evaluator = Evaluator(entity)
                        if not evaluator.evaluate(entity_filter.where_clause_ast):
                            continue
                    except Exception:
                        logger.exception(f"Failed to evaluate WHERE clause for entity {entity.get('id')}")
                        continue

                yield entity
                count += 1

                if limit and count >= limit:
                    return


def create_entity_iterator(
    db: Optional[Session] = None,
    workspace_client: Optional[Any] = None
) -> EntityIterator:
    """Create an entity iterator with standard loaders.

    Args:
        db: Database session for app entities
        workspace_client: Databricks workspace client for UC entities

    Returns:
        Configured EntityIterator
    """
    loaders = []

    if workspace_client:
        loaders.append(UnityCatalogLoader(workspace_client))

    if db:
        loaders.append(AppEntityLoader(db))

    return EntityIterator(loaders)


def parse_entity_filter(rule: str) -> EntityFilter:
    """Parse entity filter from DSL rule.

    Args:
        rule: DSL rule string with MATCH and optional WHERE clauses

    Returns:
        EntityFilter object

    Example:
        >>> rule = "MATCH (obj:Object) WHERE obj.type IN ['table', 'view']"
        >>> filter = parse_entity_filter(rule)
    """
    from src.common.compliance_dsl import parse_rule

    parsed = parse_rule(rule)

    # Extract entity types
    entity_types = []
    match_type = parsed.get('match_type')
    if match_type:
        # Generic type 'Object' means all types
        if match_type.lower() == 'object':
            entity_types = ['catalog', 'schema', 'table', 'view', 'function', 'volume',
                           'data_product', 'data_contract', 'domain', 'glossary_term']
        else:
            entity_types = [match_type.lower()]

    # If WHERE clause contains obj.type IN [...], extract specific types
    where_clause = parsed.get('where_clause')
    if where_clause:
        # Try to extract type filter from WHERE clause
        # This is a simplified extraction - in practice you might want to
        # evaluate the WHERE clause more intelligently
        pass

    return EntityFilter(
        entity_types=entity_types,
        where_clause_ast=where_clause
    )
