"""create chit installments

Revision ID: 66847ed2df47
Revises: a25dfdbba8f9
Create Date: 2026-08-28 17:10:05.224513

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "66847ed2df47"

down_revision: Union[str, Sequence[str], None] = "a25dfdbba8f9"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.create_table(
        "chit_installments",

        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "chit_member_id",
            sa.BigInteger(),
            nullable=False,
        ),

        sa.Column(
            "installment_number",
            sa.BigInteger(),
            nullable=False,
        ),

        sa.Column(
            "due_date",
            sa.Date(),
            nullable=False,
        ),

        sa.Column(
            "due_amount",
            sa.Numeric(12, 2),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["chit_member_id"],
            ["chit_members.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),
    )


    # Indexes

    op.create_index(
        "ix_chit_installments_chit_member_id",
        "chit_installments",
        ["chit_member_id"],
        unique=False,
    )

    op.create_index(
        "ix_chit_installments_status",
        "chit_installments",
        ["status"],
        unique=False,
    )


def downgrade() -> None:

    op.drop_index(
        "ix_chit_installments_status",
        table_name="chit_installments",
    )

    op.drop_index(
        "ix_chit_installments_chit_member_id",
        table_name="chit_installments",
    )

    op.drop_table(
        "chit_installments",
    )