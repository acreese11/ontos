"""Drop legacy dataset tables

The legacy Dataset entity has been superseded by the ontology-driven
Asset model.  Migration a1_dataset_to_asset_migration already copied
all data into the assets / entity_relationships / entity_subscriptions
tables.  This migration drops the now-empty legacy tables.

Revision ID: c1_drop_datasets
Revises: b3_cert_ds_asset
Create Date: 2026-03-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c1_drop_datasets"
down_revision: Union[str, None] = "b3_cert_ds_asset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Child tables first (FK constraints reference datasets.id)
    op.drop_table("dataset_instances")
    op.drop_table("dataset_custom_properties")
    op.drop_table("dataset_subscriptions")
    op.drop_table("datasets")


def downgrade() -> None:
    # Recreate in dependency order: parent first, then children
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("catalog_name", sa.String(), nullable=True),
        sa.Column("schema_name", sa.String(), nullable=True),
        sa.Column("object_name", sa.String(), nullable=True),
        sa.Column("environment", sa.String(), nullable=True),
        sa.Column("contract_id", sa.String(), nullable=True),
        sa.Column("owner_team_id", sa.String(), nullable=True),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("version", sa.String(), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("certification_level", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["contract_id"], ["data_contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "dataset_subscriptions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("subscriber_email", sa.String(), nullable=False),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("subscription_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("dataset_id", "subscriber_email", name="uq_dataset_subscriber"),
    )

    op.create_table(
        "dataset_custom_properties",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("property", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "dataset_instances",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("contract_id", sa.String(), nullable=True),
        sa.Column("contract_server_id", sa.String(), nullable=True),
        sa.Column("physical_path", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("asset_type", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("environment", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
    )
