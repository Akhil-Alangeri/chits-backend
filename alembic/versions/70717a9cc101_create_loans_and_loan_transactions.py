"""create loans and loan transactions

Revision ID: 70717a9cc101
Revises: 303f96a85571
Create Date: 2026-09-07 15:32:44.800865

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "70717a9cc101"
down_revision: Union[str, Sequence[str], None] = "303f96a85571"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =====================================================
    # LOANS
    # =====================================================

    op.create_table(
        "loans",

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

        # Person details
        sa.Column(
            "person_name",
            sa.String(length=150),
            nullable=False,
        ),

        sa.Column(
            "person_mobile",
            sa.String(length=20),
            nullable=True,
        ),

        sa.Column(
            "person_address",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),

        # given / taken
        sa.Column(
            "direction",
            sa.String(length=20),
            nullable=False,
        ),

        # Principal
        sa.Column(
            "principal_amount",
            sa.Numeric(12, 2),
            nullable=False,
        ),

        # Interest
        sa.Column(
            "interest_rate",
            sa.Numeric(8, 4),
            nullable=False,
            server_default="0",
        ),

        # monthly / yearly / one_time
        sa.Column(
            "interest_type",
            sa.String(length=20),
            nullable=False,
            server_default="monthly",
        ),

        # Dates
        sa.Column(
            "start_date",
            sa.Date(),
            nullable=False,
        ),

        sa.Column(
            "due_date",
            sa.Date(),
            nullable=True,
        ),

        # active / partially_settled / closed / cancelled
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="active",
        ),

        # Created by
        sa.Column(
            "created_by",
            sa.BigInteger(),
            nullable=True,
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

        # Primary key
        sa.PrimaryKeyConstraint("id"),

        # Foreign keys
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
        ),

        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
    )

    # Indexes
    op.create_index(
        "ix_loans_company_id",
        "loans",
        ["company_id"],
    )

    op.create_index(
        "ix_loans_direction",
        "loans",
        ["direction"],
    )

    op.create_index(
        "ix_loans_status",
        "loans",
        ["status"],
    )

    # =====================================================
    # LOAN TRANSACTIONS
    # =====================================================

    op.create_table(
        "loan_transactions",

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
            "loan_id",
            sa.BigInteger(),
            nullable=False,
        ),

        sa.Column(
            "transaction_date",
            sa.Date(),
            nullable=False,
        ),

        # disbursement
        # principal_repayment
        # interest_payment
        # adjustment
        sa.Column(
            "transaction_type",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "principal_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "interest_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),

        # cash / upi / bank / other
        sa.Column(
            "payment_method",
            sa.String(length=20),
            nullable=True,
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
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),

        # Primary key
        sa.PrimaryKeyConstraint("id"),

        # Foreign keys
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
        ),

        sa.ForeignKeyConstraint(
            ["loan_id"],
            ["loans.id"],
        ),

        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
    )

    # Indexes
    op.create_index(
        "ix_loan_transactions_company_id",
        "loan_transactions",
        ["company_id"],
    )

    op.create_index(
        "ix_loan_transactions_loan_id",
        "loan_transactions",
        ["loan_id"],
    )

    op.create_index(
        "ix_loan_transactions_transaction_date",
        "loan_transactions",
        ["transaction_date"],
    )

    op.create_index(
        "ix_loan_transactions_transaction_type",
        "loan_transactions",
        ["transaction_type"],
    )


def downgrade() -> None:
    # =====================================================
    # REMOVE LOAN TRANSACTION INDEXES
    # =====================================================

    op.drop_index(
        "ix_loan_transactions_transaction_type",
        table_name="loan_transactions",
    )

    op.drop_index(
        "ix_loan_transactions_transaction_date",
        table_name="loan_transactions",
    )

    op.drop_index(
        "ix_loan_transactions_loan_id",
        table_name="loan_transactions",
    )

    op.drop_index(
        "ix_loan_transactions_company_id",
        table_name="loan_transactions",
    )

    op.drop_table("loan_transactions")

    # =====================================================
    # REMOVE LOAN INDEXES
    # =====================================================

    op.drop_index(
        "ix_loans_status",
        table_name="loans",
    )

    op.drop_index(
        "ix_loans_direction",
        table_name="loans",
    )

    op.drop_index(
        "ix_loans_company_id",
        table_name="loans",
    )

    op.drop_table("loans")