"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Organisations
    op.create_table(
        'organisations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_organisations_slug', 'organisations', ['slug'], unique=True)

    # Users
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('google_id', sa.String(255), nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True),
                   sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.Enum('admin', 'member', name='userrole'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_google_id', 'users', ['google_id'], unique=True)
    op.create_index('ix_users_organisation_id', 'users', ['organisation_id'])

    # Credit Transactions
    op.create_table(
        'credit_transactions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('organisation_id', UUID(as_uuid=True),
                   sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True),
                   sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('amount', sa.Integer, nullable=False),
        sa.Column('reason', sa.Text, nullable=False),
        sa.Column('idempotency_key', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_credit_transactions_organisation_id',
                     'credit_transactions', ['organisation_id'])
    op.create_index('ix_credit_transactions_user_id',
                     'credit_transactions', ['user_id'])
    op.create_index('ix_credit_transactions_org_created',
                     'credit_transactions', ['organisation_id', 'created_at'])
    op.create_index('ix_credit_transactions_idempotency',
                     'credit_transactions', ['idempotency_key'],
                     unique=True,
                     postgresql_where=sa.text('idempotency_key IS NOT NULL'))

    # Jobs
    op.create_table(
        'jobs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('organisation_id', UUID(as_uuid=True),
                   sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True),
                   sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed',
                                     name='jobstatus'), nullable=False),
        sa.Column('result', sa.Text, nullable=True),
        sa.Column('error', sa.Text, nullable=True),
        sa.Column('input_text', sa.Text, nullable=False),
        sa.Column('credit_transaction_id', UUID(as_uuid=True),
                   sa.ForeignKey('credit_transactions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('idempotency_key', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_jobs_organisation_id', 'jobs', ['organisation_id'])
    op.create_index('ix_jobs_idempotency_key', 'jobs', ['idempotency_key'])


def downgrade() -> None:
    op.drop_table('jobs')
    op.drop_table('credit_transactions')
    op.drop_table('users')
    op.drop_table('organisations')
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS jobstatus")
