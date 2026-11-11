"""Add owner_id to projects table.

Revision ID: 20260923_02
Revises: 20260919_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260923_02"
down_revision = "20260919_01"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()
    if "projects" in tables:
        columns = {col["name"] for col in inspector.get_columns("projects")}
        if "owner_id" not in columns:
            op.add_column("projects", sa.Column("owner_id", sa.String(length=64), nullable=True))
            op.create_index("ix_projects_owner_id", "projects", ["owner_id"], unique=False)


def downgrade():
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()
    if "projects" in tables:
        indexes = {idx["name"] for idx in inspector.get_indexes("projects")}
        if "ix_projects_owner_id" in indexes:
            op.drop_index("ix_projects_owner_id", table_name="projects")
        columns = {col["name"] for col in inspector.get_columns("projects")}
        if "owner_id" in columns:
            op.drop_column("projects", "owner_id")
