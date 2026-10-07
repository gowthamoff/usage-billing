"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "meters",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
    )
    op.create_table(
        "plan_meters",
        sa.Column("plan_id", sa.Text(), sa.ForeignKey("plans.id"), primary_key=True),
        sa.Column("meter_id", sa.Text(), sa.ForeignKey("meters.id"), primary_key=True),
        sa.Column("allowance", sa.BigInteger(), nullable=False),
        sa.Column("overage_rate_minor", sa.Numeric(14, 6), nullable=False),
    )
    op.create_table(
        "customers",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("signup_date", sa.Date(), nullable=False),
        sa.Column("plan_id", sa.Text(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "usage_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("customer_id", sa.Text(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("meter_id", sa.Text(), sa.ForeignKey("meters.id"), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("billing_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_late", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.CheckConstraint("quantity > 0", name="ck_usage_events_quantity_positive"),
    )
    op.create_index(
        "ix_usage_events_customer_meter_occurred", "usage_events", ["customer_id", "meter_id", "occurred_at"]
    )
    op.create_index("ix_usage_events_customer_period", "usage_events", ["customer_id", "billing_period_start"])
    op.create_table(
        "usage_counters",
        sa.Column("customer_id", sa.Text(), sa.ForeignKey("customers.id"), primary_key=True),
        sa.Column("meter_id", sa.Text(), sa.ForeignKey("meters.id"), primary_key=True),
        sa.Column("period_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "threshold_notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.Text(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("meter_id", sa.Text(), sa.ForeignKey("meters.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("threshold", sa.SmallInteger(), nullable=False),
        sa.Column("usage_at_fire", sa.BigInteger(), nullable=False),
        sa.Column("allowance", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "customer_id", "meter_id", "period_start", "threshold", name="uq_threshold_notifications_once_per_cycle"
        ),
        sa.CheckConstraint("threshold > 0", name="ck_threshold_notifications_threshold_positive"),
    )
    op.create_table(
        "invoices",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("customer_id", sa.Text(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'INR'")),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'issued'")),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("customer_id", "period_start", name="uq_invoices_customer_period"),
    )
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("invoice_id", sa.Text(), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("line_type", sa.Text(), nullable=False),
        sa.Column("meter_id", sa.Text(), sa.ForeignKey("meters.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("allowance", sa.BigInteger(), nullable=False),
        sa.Column("overage_units", sa.BigInteger(), nullable=False),
        sa.Column("rate_minor", sa.Numeric(14, 6), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("adjusts_invoice_id", sa.Text(), sa.ForeignKey("invoices.id"), nullable=True),
        sa.CheckConstraint("line_type IN ('usage', 'adjustment')", name="ck_invoice_lines_line_type"),
    )
    op.create_index("ix_invoice_lines_invoice", "invoice_lines", ["invoice_id"])
    op.create_index("ix_invoice_lines_period_start", "invoice_lines", ["period_start"])


def downgrade() -> None:
    op.drop_index("ix_invoice_lines_period_start", table_name="invoice_lines")
    op.drop_index("ix_invoice_lines_invoice", table_name="invoice_lines")
    op.drop_table("invoice_lines")
    op.drop_table("invoices")
    op.drop_table("threshold_notifications")
    op.drop_table("usage_counters")
    op.drop_index("ix_usage_events_customer_period", table_name="usage_events")
    op.drop_index("ix_usage_events_customer_meter_occurred", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_table("customers")
    op.drop_table("plan_meters")
    op.drop_table("meters")
    op.drop_table("plans")
