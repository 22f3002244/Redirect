"""Add cached table extraction and generation cache.

Revision ID: 20260919_01
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "20260919_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()
    if "projects" not in tables:
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.String(length=36), nullable=False, unique=True),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("file_content", sa.Text(), nullable=False),
            sa.Column("file_extension", sa.String(length=10), nullable=False),
            sa.Column("extracted_tables", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        project_columns = {"extracted_tables"}
    else:
        project_columns = {column["name"] for column in inspector.get_columns("projects")}
    if "extracted_tables" not in project_columns:
        op.add_column("projects", sa.Column("extracted_tables", sa.JSON(), nullable=True))

    tables = sa.inspect(op.get_bind()).get_table_names()
    if "generation_cache" not in tables:
        op.create_table(
            "generation_cache",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("cache_key", sa.String(length=64), nullable=False),
            sa.Column("code", sa.Text(), nullable=False),
            sa.Column("language", sa.String(length=100), nullable=False),
            sa.Column("syntax_valid", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_generation_cache_cache_key",
            "generation_cache",
            ["cache_key"],
            unique=True,
        )


def downgrade():
    op.drop_index("ix_generation_cache_cache_key", table_name="generation_cache")
    op.drop_table("generation_cache")
