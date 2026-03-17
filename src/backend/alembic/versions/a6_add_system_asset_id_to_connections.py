"""add system_asset_id to connections

Revision ID: a6_conn_sys_asset
Revises: a5_fix_dm_type
Create Date: 2026-03-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision: str = "a6_conn_sys_asset"
down_revision: Union[str, None] = "a5_fix_dm_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "connections",
        sa.Column(
            "system_asset_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("connections", "system_asset_id")
