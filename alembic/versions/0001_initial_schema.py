"""initial_schema

Revision ID: 0001
Revises: 
Create Date: 2026-06-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users table
    op.create_table('users',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('password_hash', sa.String(length=256), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('viewer', 'admin')", name='users_role_check'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
    )

    # feature_baselines table
    op.create_table('feature_baselines',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('feature_name', sa.String(length=128), nullable=False),
        sa.Column('model_version', sa.String(length=64), nullable=False),
        sa.Column('raw_samples', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('sample_count', sa.Integer(), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('feature_name', 'model_version')
    )

    # drift_score_events table
    op.create_table('drift_score_events',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('window_id', sa.String(length=64), nullable=False),
        sa.Column('feature_name', sa.String(length=128), nullable=False),
        sa.Column('detector_type', sa.String(length=16), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('is_drifted', sa.Boolean(), nullable=False),
        sa.Column('model_version', sa.String(length=64), nullable=False),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sample_count', sa.Integer(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.CheckConstraint("detector_type IN ('kl', 'psi', 'mmd')", name='drift_score_events_detector_type_check'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_drift_scores_feature_time', 'drift_score_events', ['feature_name', sa.text('created_at DESC')], unique=False)

    # alert_rules table
    op.create_table('alert_rules',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('feature_name', sa.String(length=128), nullable=True),
        sa.Column('detector_type', sa.String(length=16), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('updated_by', sa.String(length=64), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.CheckConstraint("severity IN ('warning', 'critical')", name='alert_rules_severity_check'),
        sa.PrimaryKeyConstraint('id')
    )

    # alerts table
    op.create_table('alerts',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('rule_id', sa.UUID(), nullable=False),
        sa.Column('feature_name', sa.String(length=128), nullable=False),
        sa.Column('detector_type', sa.String(length=16), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('model_version', sa.String(length=64), nullable=False),
        sa.Column('window_id', sa.String(length=64), nullable=False),
        sa.Column('fired_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('suppressed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.ForeignKeyConstraint(['rule_id'], ['alert_rules.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_alerts_fired_at', 'alerts', [sa.text('fired_at DESC')], unique=False)
    op.create_index('idx_alerts_feature', 'alerts', ['feature_name', 'resolved_at'], unique=False)

    # auth_attempts table
    op.create_table('auth_attempts',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('ip_address', postgresql.INET(), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('attempted_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_auth_attempts_ip_time', 'auth_attempts', ['ip_address', sa.text('attempted_at DESC')], unique=False)

    # audit_log table
    op.create_table('audit_log',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('actor_user_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('resource_type', sa.String(length=64), nullable=False),
        sa.Column('resource_id', sa.String(length=128), nullable=True),
        sa.Column('old_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('new_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('audit_log')
    op.drop_index('idx_auth_attempts_ip_time', table_name='auth_attempts')
    op.drop_table('auth_attempts')
    op.drop_index('idx_alerts_feature', table_name='alerts')
    op.drop_index('idx_alerts_fired_at', table_name='alerts')
    op.drop_table('alerts')
    op.drop_table('alert_rules')
    op.drop_index('idx_drift_scores_feature_time', table_name='drift_score_events')
    op.drop_table('drift_score_events')
    op.drop_table('feature_baselines')
    op.drop_table('users')
