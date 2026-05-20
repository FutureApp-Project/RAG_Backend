"""add client error reports

Revision ID: d4b4d8f0c6a1
Revises: 29afeca44c18
Create Date: 2026-04-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4b4d8f0c6a1"
down_revision: Union[str, Sequence[str], None] = "29afeca44c18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("client_error_reports"):
        op.create_table(
            "client_error_reports",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("app", sa.String(length=64), nullable=False),
            sa.Column("source", sa.String(length=128), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("fingerprint", sa.String(length=128), nullable=False),
            sa.Column("stack", sa.Text(), nullable=True),
            sa.Column("url", sa.String(length=2000), nullable=True),
            sa.Column("route", sa.String(length=512), nullable=True),
            sa.Column("user_agent", sa.String(length=1024), nullable=True),
            sa.Column("client_ip", sa.String(length=64), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column(
                "deduplicated", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        inspector = sa.inspect(bind)

    existing_indexes = {
        index["name"] for index in inspector.get_indexes("client_error_reports")
    }
    desired_indexes = [
        (op.f("ix_client_error_reports_app"), ["app"]),
        (op.f("ix_client_error_reports_created_at"), ["created_at"]),
        (op.f("ix_client_error_reports_fingerprint"), ["fingerprint"]),
        (op.f("ix_client_error_reports_id"), ["id"]),
        (op.f("ix_client_error_reports_route"), ["route"]),
        (op.f("ix_client_error_reports_source"), ["source"]),
    ]

    for index_name, columns in desired_indexes:
        if index_name not in existing_indexes:
            op.create_index(index_name, "client_error_reports", columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("client_error_reports"):
        return

    existing_indexes = {
        index["name"] for index in inspector.get_indexes("client_error_reports")
    }

    for index_name in [
        op.f("ix_client_error_reports_source"),
        op.f("ix_client_error_reports_route"),
        op.f("ix_client_error_reports_id"),
        op.f("ix_client_error_reports_fingerprint"),
        op.f("ix_client_error_reports_created_at"),
        op.f("ix_client_error_reports_app"),
    ]:
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="client_error_reports")

    op.drop_table("client_error_reports")
