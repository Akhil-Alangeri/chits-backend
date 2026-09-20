
"""create expenses table

Revision ID: 350d05fd1983
Revises: 10b47ffbc7fa
Create Date: 2026-09-08 18:46:14.266326

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "350d05fd1983"
down_revision: Union[str, Sequence[str], None] = "10b47ffbc7fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create expenses table."""

    op.create_table(
        "expenses",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "expense_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "payment_method",
            sa.String(length=10),
            nullable=False,
        ),
        sa.Column(
            "reference",
            sa.String(length=150),
            nullable=True,
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_expenses_company_id"),
        "expenses",
        ["company_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_expenses_category"),
        "expenses",
        ["category"],
        unique=False,
    )

    op.create_index(
        op.f("ix_expenses_expense_date"),
        "expenses",
        ["expense_date"],
        unique=False,
    )

    op.create_index(
        op.f("ix_expenses_payment_method"),
        "expenses",
        ["payment_method"],
        unique=False,
    )

    op.create_index(
        op.f("ix_expenses_created_by"),
        "expenses",
        ["created_by"],
        unique=False,
    )


def downgrade() -> None:
    """Drop expenses table."""

    op.drop_index(
        op.f("ix_expenses_created_by"),
        table_name="expenses",
    )

    op.drop_index(
        op.f("ix_expenses_payment_method"),
        table_name="expenses",
    )

    op.drop_index(
        op.f("ix_expenses_expense_date"),
        table_name="expenses",
    )

    op.drop_index(
        op.f("ix_expenses_category"),
        table_name="expenses",
    )

    op.drop_index(
        op.f("ix_expenses_company_id"),
        table_name="expenses",
    )

    op.drop_table("expenses")

