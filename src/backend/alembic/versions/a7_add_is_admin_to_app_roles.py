"""add is_admin flag to app_roles

Revision ID: a7_is_admin
Revises: a6_conn_sys_asset
Create Date: 2026-03-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7_is_admin"
down_revision: Union[str, None] = "a6_conn_sys_asset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_roles",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false",
                  comment="Whether this role is the admin role"),
    )
    op.execute("UPDATE app_roles SET is_admin = true WHERE name = 'Admin'")


def downgrade() -> None:
    op.drop_column("app_roles", "is_admin")
